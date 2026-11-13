"""GigSim backends used *inside* the Marketplace MCP server.

* GigSimHttp     - the real thing: REST client for the instructor's GigSim, paths from config.
* FixtureGigSim  - in-memory stand-in built from data/fixtures, for tests and for running the
                   stack before GigSim is available. Same interface, same failure modes
                   (rate limits, 5xx), so the retry/degraded-mode code is exercised.

Select with GIGSIM_BASE_URL: an http(s) URL -> GigSimHttp; `fixture://` -> FixtureGigSim.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import statistics
import uuid
from pathlib import Path
from typing import Any

import httpx

from agent.marketplace_port import MarketplaceError, MarketplaceUnavailable, RateLimited

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "data" / "fixtures"


class GigSimHttp:
    def __init__(self, cfg: dict, base_url: str, token: str | None):
        mcfg = cfg["marketplace"]
        self.paths = mcfg["gigsim"]["paths"]
        self.max_retries = mcfg.get("max_retries", 3)
        self.backoff = mcfg.get("backoff_base_s", 0.5)
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.client = httpx.AsyncClient(base_url=base_url, headers=headers, timeout=mcfg.get("timeout_s", 10))

    async def _req(self, op: str, *, params=None, json_body=None, headers=None, **path_vars) -> Any:
        method, path = self.paths[op].split(" ", 1)
        url = path.format(**path_vars)
        last: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = await self.client.request(method, url, params=params, json=json_body, headers=headers)
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
                last = MarketplaceUnavailable(f"GigSim unreachable: {exc}")
            else:
                if resp.status_code == 429:
                    wait = float(resp.headers.get("Retry-After", self.backoff * 2**attempt))
                    last = RateLimited(wait)
                    await asyncio.sleep(min(wait, 10))
                    continue
                if resp.status_code >= 500:
                    last = MarketplaceUnavailable(f"GigSim {resp.status_code}")
                elif resp.status_code >= 400:
                    raise MarketplaceError(f"GigSim {resp.status_code}: {resp.text[:200]}")
                else:
                    return resp.json()
            await asyncio.sleep(self.backoff * 2**attempt + random.random() * 0.1)
        raise last or MarketplaceUnavailable("GigSim failed")

    async def search_jobs(self, query, limit=20):
        data = await self._req("search_jobs", params={"q": query, "limit": limit})
        return data.get("jobs", data) if isinstance(data, dict) else data

    async def get_job(self, job_id):
        return await self._req("get_job", job_id=job_id)

    async def get_client_history(self, client_id):
        return await self._req("get_client_history", client_id=client_id)

    async def get_connects_balance(self, user_id):
        return await self._req("get_connects_balance", params={"user_id": user_id})

    async def get_market_stats(self, category):
        jobs = await self.search_jobs(category, limit=500)
        return market_stats(jobs, category)

    async def create_proposal_draft(self, user_id, payload, idem):
        return await self._req("create_proposal_draft", json_body={**payload, "user_id": user_id},
                               headers={"Idempotency-Key": idem})

    async def submit_proposal(self, user_id, proposal_id, idem):
        return await self._req("submit_proposal", proposal_id=proposal_id, json_body={"user_id": user_id},
                               headers={"Idempotency-Key": idem})

    async def list_messages(self, thread_id):
        data = await self._req("list_messages", thread_id=thread_id)
        return data.get("messages", data) if isinstance(data, dict) else data

    async def send_message(self, user_id, thread_id, text, idem):
        return await self._req("send_message", thread_id=thread_id, json_body={"user_id": user_id, "text": text},
                               headers={"Idempotency-Key": idem})


def market_stats(jobs: list[dict], category: str) -> dict:
    """Budget percentiles for a category, from historical jobs (Pricing Strategist input)."""
    same = [j for j in jobs if j.get("category") == category] or jobs
    fixed = [ (j["budget"]["min"] + j["budget"]["max"]) / 2 for j in same
              if j.get("budget", {}).get("type", "fixed") == "fixed" and j["budget"].get("max")]
    hourly = [ (j["budget"]["min"] + j["budget"]["max"]) / 2 for j in same
               if j.get("budget", {}).get("type") == "hourly" and j["budget"].get("max")]

    def pct(xs):
        if not xs:
            return None
        xs = sorted(xs)
        q = statistics.quantiles(xs, n=4) if len(xs) > 1 else [xs[0]] * 3
        return {"p25": q[0], "p50": q[1], "p75": q[2], "n": len(xs)}

    return {"category": category, "fixed": pct(fixed), "hourly": pct(hourly)}


class FixtureGigSim:
    """In-memory GigSim stand-in. Not the instructor's simulator; same contract as GigSimHttp."""

    def __init__(self, fail_rate: float = 0.0, seed: int = 7, connects: int = 80):
        self.jobs = {j["job_id"]: j for j in json.loads((FIXTURES / "jobs.json").read_text())}
        self.clients = json.loads((FIXTURES / "clients.json").read_text())
        self.threads = {t["thread_id"]: t for t in json.loads((FIXTURES / "threads.json").read_text())}
        self.connects: dict[str, int] = {}
        self.start_connects = connects
        self.proposals: dict[str, dict] = {}
        self.sent_messages: list[dict] = []
        self.submissions: list[dict] = []   # every *effective* submit, for exactly-once tests
        self.fail_rate = fail_rate
        self.down = False
        self._rng = random.Random(seed)

    def _maybe_fail(self):
        if self.down:
            raise MarketplaceUnavailable("GigSim fixture is down")
        if self.fail_rate and self._rng.random() < self.fail_rate:
            raise MarketplaceUnavailable("GigSim fixture 503")

    async def search_jobs(self, query, limit=20):
        self._maybe_fail()
        terms = [t for t in query.lower().split() if len(t) > 2]
        scored = []
        for job in self.jobs.values():
            blob = (job["title"] + " " + job["description"] + " " + " ".join(job["required_skills"])).lower()
            hits = sum(t in blob for t in terms)
            if hits or not terms:
                scored.append((hits, job))
        scored.sort(key=lambda x: (-x[0], x[1]["job_id"]))
        return [j for _, j in scored[:limit]]

    async def get_job(self, job_id):
        self._maybe_fail()
        if job_id not in self.jobs:
            raise MarketplaceError(f"job {job_id} not found")
        return self.jobs[job_id]

    async def get_client_history(self, client_id):
        self._maybe_fail()
        return self.clients.get(client_id, {"client_id": client_id, "payment_verified": False, "hires": 0})

    async def get_connects_balance(self, user_id):
        self._maybe_fail()
        return {"user_id": user_id, "balance": self.connects.setdefault(user_id, self.start_connects)}

    async def get_market_stats(self, category):
        self._maybe_fail()
        return market_stats(list(self.jobs.values()), category)

    async def create_proposal_draft(self, user_id, payload, idem):
        self._maybe_fail()
        job = await self.get_job(payload["job_id"])
        pid = "P-" + uuid.uuid5(uuid.NAMESPACE_OID, idem).hex[:10]
        self.proposals.setdefault(pid, {"proposal_id": pid, "user_id": user_id, "status": "draft",
                                        "connects_cost": job["connects_cost"], **payload})
        return self.proposals[pid]

    async def submit_proposal(self, user_id, proposal_id, idem):
        self._maybe_fail()
        prop = self.proposals.get(proposal_id)
        if prop is None:
            raise MarketplaceError(f"proposal {proposal_id} not found")
        if prop["status"] == "submitted":  # GigSim itself is idempotent per proposal
            return prop
        bal = self.connects.setdefault(user_id, self.start_connects)
        if bal < prop["connects_cost"]:
            raise MarketplaceError("insufficient connects")
        self.connects[user_id] = bal - prop["connects_cost"]
        prop["status"] = "submitted"
        self.submissions.append({"proposal_id": proposal_id, "idem": idem})
        return prop

    async def list_messages(self, thread_id):
        self._maybe_fail()
        return list(self.threads.get(thread_id, {}).get("messages", []))

    async def send_message(self, user_id, thread_id, text, idem):
        self._maybe_fail()
        msg = {"id": "m-" + idem[:8], "sender": "freelancer", "text": text, "thread_id": thread_id}
        self.sent_messages.append(msg)
        self.threads.setdefault(thread_id, {"messages": []})["messages"].append(msg)
        return msg


def make_backend(cfg: dict):
    base = os.environ.get(cfg["marketplace"]["gigsim"]["base_url_env"], "fixture://")
    if base.startswith("fixture://"):
        return FixtureGigSim()
    return GigSimHttp(cfg, base, os.environ.get(cfg["marketplace"]["gigsim"]["token_env"]))
