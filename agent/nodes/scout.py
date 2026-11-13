"""Scout: run saved searches on a schedule, de-duplicate, queue new jobs; and the bid graph's entry
node that hands one job in.

De-duplication is by a content fingerprint (normalised title + description), not by job id,
because reposts get new ids. Seen fingerprints live in the store namespace
("users", user, "seen_jobs") - operational state, not long-term memory.
"""
from __future__ import annotations

import hashlib
import re

from agent.guardrails import detect_injection
from agent.nodes.common import ctx_of, node


def fingerprint(job: dict) -> str:
    norm = re.sub(r"\W+", " ", (job.get("title", "") + " " + job.get("description", "")).lower()).strip()
    return hashlib.sha256(norm.encode()).hexdigest()[:24]


async def scout_saved_searches(port, store, user_id: str, searches: list[str], limit: int = 20) -> list[dict]:
    """Called by the worker on each saved search's schedule. Returns only new, unseen jobs."""
    ns = ("users", user_id, "seen_jobs")
    new = []
    for query in searches:
        for job in await port.search_jobs(query, limit):
            fp = fingerprint(job)
            if await store.aget(ns, fp) is not None:
                continue
            await store.aput(ns, fp, {"job_id": job["job_id"]})
            new.append(job)
    return new


@node("scout")
async def scout_intake(state, runtime):
    """Bid-graph entry: fetch the job if only an id was given, and stop exact duplicates."""
    ctx = ctx_of(runtime)
    job = state.get("job")
    if not job:
        job = await ctx.marketplace("scout").get_job(state["job_id"])
    out = {"job": job, "job_id": job["job_id"], "status": "running"}
    store = runtime.store
    if store is not None:
        ns = ("users", ctx.user_id, "seen_jobs")
        fp = fingerprint(job)
        seen = await store.aget(ns, fp)
        if seen is not None and seen.value.get("job_id") != job["job_id"]:
            out.update(status="skipped", status_reason=f"duplicate of {seen.value['job_id']}",
                       decision={"action": "skip", "reasons": [f"duplicate of {seen.value['job_id']}"], "auto": True})
            return out
        await store.aput(ns, fp, {"job_id": job["job_id"]})
    hits = detect_injection(job.get("description", ""))
    out["trace"] = [{"node": "scout", "injection_patterns": len(hits)}]
    return out
