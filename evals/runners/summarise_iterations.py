"""Summarise decision-eval runs under evals/results/iterations/<run>/ into one CSV + Markdown table.

    python -m evals.runners.summarise_iterations
"""
from __future__ import annotations

import csv
import json

from agent.config import ROOT

KEYS = ["bid_skip_f1", "scam_precision", "scam_recall", "injections_followed", "price_in_fair_band",
        "unsupported_per_proposal_before", "unsupported_per_proposal_after", "p95_latency_s_per_job"]


def rows():
    base = ROOT / "evals" / "results" / "iterations"
    for run in sorted(p for p in base.iterdir() if p.is_dir()):
        for f in sorted(run.glob("decision_*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            yield {"run": run.name, "dataset": d["dataset"], **{k: d["summary"].get(k) for k in KEYS}, "file": f.name}


def main():
    out = list(rows())
    base = ROOT / "evals" / "results" / "iterations"
    with open(base / "summary.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["run", "dataset", *KEYS, "file"])
        w.writeheader()
        w.writerows(out)
    lines = ["| run | dataset | " + " | ".join(KEYS) + " |", "|" + "---|" * (len(KEYS) + 2)]
    lines += [f"| {r['run']} | {r['dataset']} | " + " | ".join("" if r[k] is None else str(r[k]) for k in KEYS) + " |" for r in out]
    (base / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
