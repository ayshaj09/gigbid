"""Local marketplace simulator (replaces GigSim, which this course run does not provide).

Serves the job pool built by `datapipe.build` (real Kaggle job posts + clearly marked synthetic
fields) through the same backend contract as GigSimHttp, and simulates client behaviour.

CLIENT REPLY MODEL (synthetic; documented so results can be interpreted honestly)
    logit = -4.0
            + 1.2 * client_quality                     (synthetic client history, 0..1)
            + 1.2 * specificity                        (share of the job's content words the letter uses, capped at 0.5 -> x2)
            + 0.8 * skills_mentioned                   (share of required skills named in the letter)
            + 0.9 * price_fit                          (1 inside the client's range, decays outside)
            - 1.5 * generic                            (generic phrases: "I am passionate", "I have read your job post"...)
            - 0.8 * too_long                           (over 350 words)
    p_reply = sigmoid(logit); outcome drawn with a RNG seeded by the proposal id (reproducible).
    p_hire  = 0.35 * p_reply if replied.
The model rewards exactly the properties GigBid tries to optimise, so simulated reply rates
measure "does the agent produce specific, well-priced, non-generic proposals", NOT real-world
reply rates. Say this wherever simulated outcomes are reported. Calibration target: a generic
proposal replies ~3% of the time, a specific, well-priced one to a good client ~35%, in the range
of published freelance-marketplace reply rates; tune b0 if your pilot shows otherwise.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import re
from pathlib import Path

from agent.marketplace_port import MarketplaceError
from mcp_servers.marketplace.adapters.gigsim import FixtureGigSim
from rag.text import content_set

ROOT = Path(__file__).resolve().parents[3]
GENERIC = ["i am passionate", "i have read your job", "dear sir", "many years of experience", "i am confident i can",
           "hardworking", "perfect fit for this job"]


def client_quality(h: dict) -> float:
    from agent.nodes.risk_assessor import client_quality as cq

    return cq(h)


def reply_probability(job: dict, client: dict, letter: str, bid: float) -> tuple[float, dict]:
    jw = content_set(job.get("title", "") + " " + job.get("description", ""))
    lw = content_set(letter)
    specificity = min(len(jw & lw) / max(len(jw), 1), 0.5) * 2
    skills = job.get("required_skills") or []
    skills_mentioned = sum(s.lower() in letter.lower() for s in skills) / len(skills) if skills else 0.5
    b = job.get("budget") or {}
    lo, hi = b.get("min") or 0, b.get("max") or 0
    if not hi:
        price_fit = 0.6
    elif (lo * 0.8) <= bid <= hi * 1.1:
        price_fit = 1.0
    else:
        price_fit = max(0.0, 1 - abs(bid - hi) / max(hi, 1))
    generic = float(any(g in letter.lower() for g in GENERIC))
    too_long = float(len(letter.split()) > 350)
    feats = {"client_quality": client_quality(client), "specificity": round(specificity, 3),
             "skills_mentioned": round(skills_mentioned, 3), "price_fit": round(price_fit, 3),
             "generic": generic, "too_long": too_long}
    logit = (-4.0 + 1.2 * feats["client_quality"] + 1.2 * specificity + 0.8 * skills_mentioned + 0.9 * price_fit
             - 1.5 * generic - 0.8 * too_long)
    return 1 / (1 + math.exp(-logit)), feats


class LocalSim(FixtureGigSim):
    """In-process simulator over data/market (see module docstring for the reply model)."""

    def __init__(self, data_dir: Path | None = None, connects: int = 400, seed: int = 7):
        super().__init__(connects=connects, seed=seed)
        d = Path(data_dir or ROOT / "data" / "market")
        if not (d / "jobs.json").exists():
            raise FileNotFoundError(f"{d}/jobs.json missing: run `python -m datapipe.build` first")
        self.jobs = {j["job_id"]: j for j in json.loads((d / "jobs.json").read_text(encoding="utf-8"))}
        self.clients = json.loads((d / "clients.json").read_text(encoding="utf-8"))
        self.threads = {t["thread_id"]: t for t in json.loads((d / "threads.json").read_text(encoding="utf-8"))}
        self.stats = json.loads((d / "market_stats.json").read_text(encoding="utf-8"))

    async def search_jobs(self, query, limit=20):
        self._maybe_fail()
        terms = [t for t in re.findall(r"\w+", query.lower()) if len(t) > 2]
        scored = []
        for job in self.jobs.values():
            if job.get("planted_injection") or job.get("source") == "fake_job_postings":
                continue  # eval-only jobs are not in the live feed
            blob = (job["title"] + " " + " ".join(job.get("required_skills", []))).lower()
            hits = sum(t in blob for t in terms)
            if hits:
                scored.append((hits, job.get("posted_at") or "", job))
        scored.sort(key=lambda x: x[1], reverse=True)   # newest first...
        scored.sort(key=lambda x: -x[0])                # ...within best keyword match (stable sort)
        return [j for _, _, j in scored[:limit]]

    async def get_market_stats(self, category):
        self._maybe_fail()
        s = self.stats.get(category) or {"category": category}
        return {"category": category, "fixed": s.get("fixed"), "hourly": s.get("hourly")}

    async def submit_proposal(self, user_id, proposal_id, idem):
        prop = await super().submit_proposal(user_id, proposal_id, idem)
        if "client_replied" not in prop:
            job = self.jobs[prop["job_id"]]
            client = self.clients.get(job.get("client_id"), {})
            p, feats = reply_probability(job, client, prop.get("cover_letter", ""), float(prop.get("bid_amount") or 0))
            r = random.Random(int(hashlib.sha256(proposal_id.encode()).hexdigest()[:12], 16))
            replied = r.random() < p
            prop.update(client_replied=replied, hired=replied and r.random() < 0.35,
                        reply_probability=round(p, 4), reply_features=feats, simulated=True)
            if replied:
                tid = "T-" + proposal_id
                self.threads[tid] = {"thread_id": tid, "job_id": job["job_id"], "synthetic": True, "messages": [
                    {"id": tid + "-1", "sender": "freelancer", "text": "(proposal sent)"},
                    {"id": tid + "-2", "sender": "client",
                     "text": r.choice(["Thanks, this looks relevant. Could we do a short call this week?",
                                       "How soon could you start, and what would you need from us?",
                                       "Interesting. Can you do it for a bit less?"])}]}
                prop["thread_id"] = tid
        return prop

    async def get_proposal(self, proposal_id):
        self._maybe_fail()
        if proposal_id not in self.proposals:
            raise MarketplaceError(f"proposal {proposal_id} not found")
        return self.proposals[proposal_id]
