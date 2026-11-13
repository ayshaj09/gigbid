"""Run, pause, resume and recover graph threads (C5, C6, C7). Used by the worker, the API and tests.

Thread ids: "<user>:job:<job_id>" and "<user>:thread:<thread_id>", so a page refresh (or an API
restart) finds the pending approval again from the checkpointer.

Durability: `persistence()` yields a Postgres checkpointer + store when DATABASE_URL is a Postgres
URL, else SQLite (checkpoints) + in-memory store. Kill the process while a proposal waits for
approval, restart, call `resume_job(...)`: the thread continues from its checkpoint and the
idempotency keys make the submission happen exactly once.

Degraded mode: if a marketplace call still fails after node retries, the thread stays at its last
checkpoint with status `waiting_for_marketplace`; `retry_waiting()` resumes those threads.
"""
from __future__ import annotations

import contextlib
import os
import uuid
from dataclasses import dataclass, field
from typing import Any

from langgraph.types import Command

from agent.graphs.bid_graph import compile_bid_graph
from agent.graphs.conversation_graph import compile_conversation_graph
from agent.llm import LLMRouter
from agent.marketplace_port import MarketplaceUnavailable
from agent.nodes.common import GigBidContext


@contextlib.asynccontextmanager
async def persistence(cfg: dict, sqlite_path: str | None = None):
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres"):
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from langgraph.store.postgres.aio import AsyncPostgresStore

        pg = url.replace("postgresql+psycopg://", "postgresql://")
        async with AsyncPostgresSaver.from_conn_string(pg) as saver, AsyncPostgresStore.from_conn_string(pg) as store:
            await saver.setup()
            await store.setup()
            yield saver, store
        return
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from langgraph.store.sqlite.aio import AsyncSqliteStore

    path = sqlite_path or os.environ.get("GIGBID_SQLITE", "data/processed/checkpoints.sqlite")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(path) as saver, AsyncSqliteStore.from_conn_string(path + ".store") as store:
        await store.setup()
        yield saver, store


@dataclass
class RunResult:
    thread_id: str
    status: str
    state: dict
    interrupt: Any = None
    error: str | None = None
    events: list[dict] = field(default_factory=list)


class Runner:
    def __init__(self, cfg: dict, belt, persona: dict, checkpointer, store, user_id: str = "default",
                 marketplace_override=None, llm: LLMRouter | None = None):
        self.cfg = cfg
        self.belt = belt
        self.persona = persona
        self.user_id = user_id
        self.store = store
        self.llm = llm or LLMRouter(cfg)
        self.marketplace_override = marketplace_override
        self.bid = compile_bid_graph(checkpointer, store, cfg["budgets"]["max_revisions"])
        self.conv = compile_conversation_graph(checkpointer, store)
        self.waiting: set[tuple[str, str]] = set()  # (graph, thread_id) parked in degraded mode

    def _ctx(self, trace_id: str) -> GigBidContext:
        return GigBidContext(cfg=self.cfg, belt=self.belt, llm=self.llm, persona=self.persona, user_id=self.user_id,
                             trace_id=trace_id, marketplace_override=self.marketplace_override)

    def job_thread(self, job_id: str) -> str:
        return f"{self.user_id}:job:{job_id}"

    def conv_thread(self, thread_id: str) -> str:
        return f"{self.user_id}:thread:{thread_id}"

    async def _run(self, graph_name: str, thread: str, payload, stream_cb=None) -> RunResult:
        graph = self.bid if graph_name == "bid" else self.conv
        config = {"configurable": {"thread_id": thread}, "recursion_limit": 80}
        trace_id = uuid.uuid4().hex[:16]
        events = []
        try:
            async for chunk in graph.astream(payload, config, context=self._ctx(trace_id), stream_mode="updates"):
                for node_name, update in chunk.items():
                    ev = {"node": node_name, "trace_id": trace_id,
                          "status": (update or {}).get("status") if isinstance(update, dict) else None}
                    events.append(ev)
                    if stream_cb:
                        await stream_cb(ev)
        except MarketplaceUnavailable as exc:
            self.waiting.add((graph_name, thread))
            snap = await graph.aget_state(config)
            return RunResult(thread, "waiting_for_marketplace", dict(snap.values), error=str(exc), events=events)
        self.waiting.discard((graph_name, thread))
        snap = await graph.aget_state(config)
        intr = snap.tasks[0].interrupts[0].value if snap.tasks and snap.tasks[0].interrupts else None
        status = "awaiting_approval" if intr is not None else snap.values.get("status", "unknown")
        return RunResult(thread, status, dict(snap.values), interrupt=intr, events=events)

    # ---- bid graph -------------------------------------------------------------------------
    async def start_job(self, job: dict | str, stream_cb=None) -> RunResult:
        payload = {"job": job} if isinstance(job, dict) else {"job_id": job}
        job_id = job["job_id"] if isinstance(job, dict) else job
        payload.update(user_id=self.user_id, persona_id=self.persona.get("persona_id", ""), revisions=0)
        return await self._run("bid", self.job_thread(job_id), payload, stream_cb)

    async def resume_job(self, job_id: str, decision: dict, stream_cb=None) -> RunResult:
        return await self._run("bid", self.job_thread(job_id), Command(resume=decision), stream_cb)

    async def job_state(self, job_id: str) -> RunResult:
        config = {"configurable": {"thread_id": self.job_thread(job_id)}}
        snap = await self.bid.aget_state(config)
        intr = snap.tasks[0].interrupts[0].value if snap.tasks and snap.tasks[0].interrupts else None
        return RunResult(self.job_thread(job_id), "awaiting_approval" if intr else snap.values.get("status", "none"),
                         dict(snap.values), interrupt=intr)

    async def history(self, job_id: str) -> list:
        """Checkpoint history for replay: pass any entry's config to graph.ainvoke(None, cfg) to
        replay from that node."""
        config = {"configurable": {"thread_id": self.job_thread(job_id)}}
        return [s async for s in self.bid.aget_state_history(config)]

    # ---- conversation graph ---------------------------------------------------------------
    async def start_conversation(self, thread_id: str, job_id: str | None = None, stream_cb=None) -> RunResult:
        return await self._run("conv", self.conv_thread(thread_id),
                               {"thread_id": thread_id, "job_id": job_id or "", "user_id": self.user_id}, stream_cb)

    async def resume_conversation(self, thread_id: str, decision: dict) -> RunResult:
        return await self._run("conv", self.conv_thread(thread_id), Command(resume=decision))

    # ---- degraded mode --------------------------------------------------------------------
    async def retry_waiting(self) -> list[RunResult]:
        """Resume every parked thread from its checkpoint (input None = continue)."""
        results = []
        for graph_name, thread in sorted(self.waiting):
            results.append(await self._run(graph_name, thread, None))
        return results
