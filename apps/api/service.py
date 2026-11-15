"""Application service: owns the checkpointer, store, MCP ToolBelt, per-user Runners and background runs.

MCP_MODE=inprocess (default) starts the three MCP servers inside the API process on memory
transports (one container, simplest deploy). MCP_MODE=external connects to them as separate
processes/containers per `mcp.servers` in config.yaml (stdio or Streamable HTTP).
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
import uuid
from typing import Any

from agent.config import _deep_merge, load_config
from agent.llm import LLMRouter
from agent.runner import Runner, RunResult, persistence
from apps.api.db import DB
from apps.api.security import TokenStore
from rag.retriever import load_persona

# Settings a user may change from the UI, and where each lands in the runtime config.
SETTING_PATHS = {
    "minimum_fit_score": ("thresholds", "minimum_fit_score"),
    "watch_fit_score": ("thresholds", "watch_fit_score"),
    "maximum_risk_score": ("thresholds", "maximum_risk_score"),
    "auto_skip_low_fit": ("autonomy", "auto_skip_low_fit"),
    "weekly_connects_budget": ("connects", "weekly_budget"),
    "model_profile": ("models", "profile"),
    "retrieval_variant": ("retrieval", "variant"),
}
PERSONA_FIELDS = ("hourly_rate_usd", "floor_usd", "saved_searches", "weekly_connects_budget", "display_name")


class Run:
    def __init__(self, run_id: str, user_id: str, kind: str, target: str):
        self.run_id, self.user_id, self.kind, self.target = run_id, user_id, kind, target
        self.events: list[dict] = []
        self.done = False
        self.result: RunResult | None = None
        self.cond = asyncio.Condition()
        self.started = time.time()

    async def push(self, event: dict):
        async with self.cond:
            self.events.append({**event, "ts": time.time()})
            self.cond.notify_all()

    async def finish(self, result: RunResult | None, error: str | None = None):
        async with self.cond:
            self.result = result
            self.done = True
            self.events.append({"node": "__end__", "status": result.status if result else "error",
                                "error": error or (result.error if result else None), "ts": time.time()})
            self.cond.notify_all()


class Service:
    def __init__(self):
        self.cfg = load_config()
        self.db = DB()
        self.tokens = TokenStore(self.db)
        self.runners: dict[str, Runner] = {}
        self.runs: dict[str, Run] = {}
        self.backend = None
        self.belt = None
        self.saver = self.store = None
        self._stack = contextlib.AsyncExitStack()
        self.marketplace_down_since: float | None = None

    async def start(self):
        self.saver, self.store = await self._stack.enter_async_context(persistence(self.cfg))
        if os.environ.get("MCP_MODE", "inprocess") == "inprocess":
            from agent.testing import open_inprocess_belt
            from mcp_servers.common import DATA_DIR
            from mcp_servers.marketplace.adapters.gigsim import make_backend

            self.backend = make_backend(self.cfg)
            data_dir = os.environ.get("GIGBID_DATA_DIR", str(DATA_DIR))
            self.belt, self.servers = await open_inprocess_belt(
                self._stack, self.cfg, data_dir, self.backend, os.environ.get("PORTFOLIO_PERSONA", "ai_engineer"))
        else:
            from agent.mcp_client import ToolBelt

            self.belt = await ToolBelt.connect(self.cfg)
            self._stack.push_async_callback(self.belt.close)

    async def stop(self):
        for run in self.runs.values():
            if getattr(run, "task", None) and not run.task.done():
                run.task.cancel()
        await self._stack.aclose()

    # ---- per-user runtime ------------------------------------------------------------------
    def user_cfg(self, user: dict) -> dict:
        over: dict[str, Any] = {}
        for key, (sec, field) in SETTING_PATHS.items():
            if key in user["settings"]:
                over.setdefault(sec, {})[field] = user["settings"][key]
        return _deep_merge(self.cfg, over)

    def persona(self, user: dict) -> dict:
        base = load_persona(user.get("persona_id") or "ai_engineer")
        return {**base, **{k: user["settings"][k] for k in PERSONA_FIELDS if k in user["settings"]}}

    def runner(self, user: dict) -> Runner:
        r = self.runners.get(user["id"])
        if r is None:
            cfg = self.user_cfg(user)
            override = None
            if cfg["marketplace"]["mode"] == "upwork_live":
                from mcp_servers.marketplace.adapters.upwork_live import UpworkLiveMarketplace

                override = UpworkLiveMarketplace(cfg, user_id=user["id"], token_provider=self.tokens.get)
            r = Runner(cfg, self.belt, self.persona(user), self.saver, self.store, user_id=user["id"],
                       marketplace_override=override, llm=LLMRouter(cfg))
            self.runners[user["id"]] = r
        return r

    def invalidate(self, user_id: str):
        """Settings changed: rebuild that user's Runner (threads live in the checkpointer, so nothing is lost)."""
        self.runners.pop(user_id, None)

    # ---- background runs ------------------------------------------------------------------
    def launch(self, user: dict, kind: str, target: str, fn) -> Run:
        run = Run(uuid.uuid4().hex[:12], user["id"], kind, target)
        self.runs[run.run_id] = run
        self.db.exec("INSERT INTO runs (run_id,user_id,kind,target_id,status,events,started) VALUES (?,?,?,?,?,?,?)",
                     (run.run_id, user["id"], kind, target, "running", "[]", run.started))

        async def body():
            try:
                result = await fn(run.push)
            except Exception as exc:  # noqa: BLE001 - surfaced to the UI, never crashes the API
                await run.finish(None, repr(exc))
                self.db.exec("UPDATE runs SET status=?, finished=?, error=?, events=? WHERE run_id=?",
                             ("error", time.time(), repr(exc), json.dumps(run.events), run.run_id))
                return
            self._index(user, kind, target, result)
            await run.finish(result)
            usage = result.state.get("usage") or {}
            self.db.exec("UPDATE runs SET status=?, finished=?, tokens=?, usd=?, error=?, events=? WHERE run_id=?",
                         (result.status, time.time(), usage.get("tokens_in", 0) + usage.get("tokens_out", 0),
                          usage.get("usd", 0.0), result.error, json.dumps(run.events), run.run_id))

        run.task = asyncio.create_task(body())
        return run

    def _index(self, user: dict, kind: str, target: str, result: RunResult):
        if result.status == "waiting_for_marketplace":
            self.marketplace_down_since = self.marketplace_down_since or time.time()
        elif result.status not in ("error",):
            self.marketplace_down_since = None
        s = result.state
        if kind == "job":
            job = s.get("job") or {"job_id": target, "title": target}
            self.db.upsert_job(user["id"], job, s, result.status)
        else:
            last = (s.get("last_client_message") or {}).get("text")
            self.db.exec(
                "INSERT INTO threads VALUES (?,?,?,?,?,?,?) ON CONFLICT(user_id, thread_id) DO UPDATE SET "
                "status=excluded.status, intent=excluded.intent, last_message=excluded.last_message, updated=excluded.updated",
                (user["id"], target, s.get("job_id"), result.status, (s.get("intent") or {}).get("intent"), last, time.time()))

    async def retry_waiting(self) -> list[RunResult]:
        """Resume every thread parked in degraded mode, from its checkpoint. The parked list is read
        from the database, so it survives API restarts and runner rebuilds."""
        out = []
        for row in self.db.all("SELECT user_id, job_id FROM jobs WHERE status='waiting_for_marketplace'"):
            user = self.db.user(row["user_id"])
            runner = self.runner(user)
            res = await runner._run("bid", runner.job_thread(row["job_id"]), None)
            self._index(user, "job", row["job_id"], res)
            out.append(res)
        for row in self.db.all("SELECT user_id, thread_id FROM threads WHERE status='waiting_for_marketplace'"):
            user = self.db.user(row["user_id"])
            runner = self.runner(user)
            res = await runner._run("conv", runner.conv_thread(row["thread_id"]), None)
            self._index(user, "thread", row["thread_id"], res)
            out.append(res)
        return out
