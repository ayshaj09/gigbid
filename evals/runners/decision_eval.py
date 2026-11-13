"""B4 decision + proposal metrics by running the full bid graph on a dataset.

    python -m evals.runners.decision_eval --dataset fixtures [--limit 30] [--fail-on-thresholds]
Reports bid/skip F1, scam precision/recall, price-in-fair-band, unsupported claims per proposal
(before and after verification), p50/p95 latency, tokens and USD per job and per proposal.
`--fail-on-thresholds` exits non-zero when CI gates in evals/thresholds.json are breached (E2).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import tempfile
import time

from agent.config import ROOT
from agent.testing import harness
from evals.datasets import is_smoke, load
from rag.metrics import f1, percentile


async def run(dataset: str, limit: int | None):
    jobs, gold, persona = load(dataset)
    ids = [j for j in gold if j in jobs][:limit]
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        async with harness(tmp, persona=persona) as r:
            cfg = r.cfg
            for jid in ids:
                t0 = time.perf_counter()
                res = await r.start_job(jobs[jid])
                dt = time.perf_counter() - t0
                s = res.state
                action = "bid" if res.status == "awaiting_approval" else (s.get("decision") or {}).get("action", "skip")
                ver = s.get("verification") or {}
                q = s.get("price_quote") or {}
                band = gold[jid].get("fair_band") or [0, 0]
                usage = s.get("usage") or {}
                rows.append({"job_id": jid, "gold_action": gold[jid]["action"], "action": action,
                             "gold_scam": gold[jid]["scam"], "scam": bool((s.get("risk_report") or {}).get("is_scam")),
                             "price": q.get("amount"), "in_band": (band[0] <= q["amount"] <= band[1]) if q else None,
                             "unsupported_before": ver.get("unsupported_before"), "unsupported_after": ver.get("unsupported_after"),
                             "revisions": s.get("revisions", 0), "latency_s": round(dt, 3),
                             "tokens": usage.get("tokens_in", 0) + usage.get("tokens_out", 0), "usd": usage.get("usd", 0.0),
                             "status": res.status})
    return rows, cfg


def summarise(rows):
    tp = sum(r["action"] == "bid" and r["gold_action"] == "bid" for r in rows)
    fp = sum(r["action"] == "bid" and r["gold_action"] != "bid" for r in rows)
    fn = sum(r["action"] != "bid" and r["gold_action"] == "bid" for r in rows)
    stp = sum(r["scam"] and r["gold_scam"] for r in rows)
    sfp = sum(r["scam"] and not r["gold_scam"] for r in rows)
    sfn = sum(not r["scam"] and r["gold_scam"] for r in rows)
    props = [r for r in rows if r["unsupported_before"] is not None]
    priced = [r for r in rows if r["in_band"] is not None and r["gold_action"] == "bid"]
    lat = [r["latency_s"] for r in rows]
    return {
        "n_jobs": len(rows), "bid_skip_f1": round(f1(tp, fp, fn), 4),
        "scam_precision": round(stp / (stp + sfp), 4) if stp + sfp else None,
        "scam_recall": round(stp / (stp + sfn), 4) if stp + sfn else None,
        "price_in_fair_band": round(sum(r["in_band"] for r in priced) / len(priced), 4) if priced else None,
        "unsupported_per_proposal_before": round(sum(r["unsupported_before"] for r in props) / len(props), 4) if props else None,
        "unsupported_per_proposal_after": round(sum(r["unsupported_after"] for r in props) / len(props), 4) if props else None,
        "p50_latency_s_per_job": round(percentile(lat, 50), 3), "p95_latency_s_per_job": round(percentile(lat, 95), 3),
        "tokens_per_job": round(sum(r["tokens"] for r in rows) / len(rows), 1) if rows else 0,
        "usd_per_job": round(sum(r["usd"] for r in rows) / len(rows), 6) if rows else 0,
    }


def main():
    logging.getLogger("mcp").setLevel(logging.WARNING)
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="fixtures")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--fail-on-thresholds", action="store_true")
    args = ap.parse_args()
    rows, cfg = asyncio.run(run(args.dataset, args.limit))
    summary = summarise(rows)
    out = {"dataset": args.dataset, "model_profile": cfg["models"]["profile"], "variant": cfg["retrieval"]["variant"],
           "warnings": is_smoke(args.dataset, cfg), "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "summary": summary, "rows": rows}
    path = ROOT / "evals" / "results" / f"decision_{args.dataset}_{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(out, indent=1))
    print(json.dumps(summary, indent=1))
    for w in out["warnings"]:
        print("WARNING:", w)
    print("wrote", path.relative_to(ROOT))
    if args.fail_on_thresholds:
        th = json.loads((ROOT / "evals" / "thresholds.json").read_text())
        bad = []
        if summary["bid_skip_f1"] < th["min_bid_skip_f1"]:
            bad.append(f"bid/skip F1 {summary['bid_skip_f1']} < {th['min_bid_skip_f1']}")
        if (summary["unsupported_per_proposal_after"] or 0) > th["max_unsupported_per_proposal_after"]:
            bad.append("unsupported claims after verification above threshold")
        if bad:
            print("EVAL GATE FAILED:", *bad, sep="\n  ")
            sys.exit(1)


if __name__ == "__main__":
    main()
