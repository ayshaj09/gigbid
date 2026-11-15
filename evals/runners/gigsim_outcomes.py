"""Simulated outcomes in GigSim (B4: reply rate, interview/hire rate, Connects per reply).

    python -m evals.runners.gigsim_outcomes --dataset <name> --limit 40 --wait-s 120 [--strategy writer_b]

EVALUATION ONLY, SIMULATOR ONLY: this script approves drafts automatically so the simulated
clients can respond. It runs against LocalSim (local://, built from the Kaggle data, reply model in
mcp_servers/marketplace/adapters/local_sim.py) or a real GigSim; never against live Upwork.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
import time

from agent.config import ROOT, load_config
from agent.testing import harness
from evals.datasets import backend_for, load


async def run_arm(dataset: str, job_ids: list[str], strategy: str, wait_s: int, backend=None) -> dict:
    jobs, gold, persona = load(dataset)
    rows = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        over = {"writer": {"strategy": strategy}}
        async with harness(tmp, cfg_overrides=over, backend=backend or backend_for(dataset), persona=persona) as r:
            if os.environ.get("MODEL_PROFILE"):
                r.cfg["models"]["profile"] = os.environ["MODEL_PROFILE"]
            for jid in job_ids:
                res = await r.start_job(jobs[jid])
                if res.status != "awaiting_approval":
                    rows.append({"job_id": jid, "bid": False, "status": res.status})
                    continue
                done = await r.resume_job(jid, {"action": "approve", "approver": "eval-script"})
                sub = done.state.get("submission") or {}
                rows.append({"job_id": jid, "bid": True, "status": done.status, "proposal_id": sub.get("proposal_id"),
                             "connects": (done.state.get("price_quote") or {}).get("connects_cost", 0)})
            await asyncio.sleep(wait_s)  # let the simulated clients react
            port = r._ctx("eval").marketplace("outcomes")
            for row in rows:
                if row.get("proposal_id"):
                    st = await port.get_proposal(row["proposal_id"])
                    row.update(replied=st.get("client_replied"), hired=st.get("hired"))
    bids = [x for x in rows if x.get("proposal_id")]
    replies = sum(bool(x.get("replied")) for x in bids)
    return {"strategy": strategy, "n_jobs": len(rows), "n_bids": len(bids), "replies": replies,
            "reply_rate": round(replies / len(bids), 4) if bids else None,
            "hire_rate": round(sum(bool(x.get("hired")) for x in bids) / len(bids), 4) if bids else None,
            "connects_per_reply": round(sum(x["connects"] for x in bids) / replies, 2) if replies else None,
            "unknown_outcomes": sum(x.get("replied") is None for x in bids), "rows": rows}


def _guard():
    """Outcomes only from a simulator that simulates clients: the real GigSim (http) or LocalSim (local://)."""
    cfg = load_config()
    base = os.environ.get(cfg["marketplace"]["gigsim"]["base_url_env"]) or (
        "local://" if (ROOT / "data" / "market" / "jobs.json").exists() else "fixture://")
    if cfg["marketplace"]["mode"] != "gigsim" or base.startswith("fixture://"):
        raise SystemExit("Refusing: outcomes need a simulator with client behaviour: build data/market "
                         "(python -m datapipe.build) or point GIGSIM_BASE_URL at GigSim.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--wait-s", type=int, default=0, help="seconds to wait for replies (0 for LocalSim; ~120 for a real GigSim)")
    ap.add_argument("--strategy", default="writer")
    a = ap.parse_args()
    _guard()
    jobs, gold, _ = load(a.dataset)
    ids = [j for j in gold if j in jobs][: a.limit]
    out = asyncio.run(run_arm(a.dataset, ids, a.strategy, a.wait_s))
    path = ROOT / "evals" / "results" / f"gigsim_outcomes_{a.strategy}_{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1), "\nwrote", path.relative_to(ROOT))
