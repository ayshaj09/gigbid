"""Measured failure taxonomy: categorise every failed dev job at the baseline and follow it through
the fix iterations (same dev set v1, same job ids) to see which fix, if any, repaired it.

    python -m evals.runners.failure_taxonomy
    -> evals/results/failure_taxonomy.json, evals/results/failure_taxonomy.md

Categories follow the assignment's list (missed evidence, wrong skip, mispriced, unsupported claim,
compliance miss, injection, tool error) plus the two this data needed: risk false positive /
negative, and wrong bid. Categories are assigned from each job's recorded decision reasons and
flags (auto, deterministic); spot-check them by hand before quoting.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict

from agent.config import ROOT

ITER = ROOT / "evals" / "results" / "iterations"
V1_RUNS = ["0_baseline", "1_risk_config_taxonomy", "2_intent_scam_rules", "3_tag_strength", "4_below_floor_skip"]
FIX = {"1_risk_config_taxonomy": "risk rules in config (no zero_budget for hourly, income-bait patterns) + skill taxonomy",
       "2_intent_scam_rules": "scam rules require intent toward the freelancer",
       "3_tag_strength": "skill requirements matched on evidence tags",
       "4_below_floor_skip": "skip jobs far below floor/rate"}


def categorise(r: dict) -> list[str]:
    cats = []
    reason = (r.get("decision_reasons") or [""])[0]
    if r["scam"] and not r["gold_scam"]:
        cats.append("risk_false_positive (scam)")
    if r["gold_scam"] and not r["scam"]:
        cats.append("risk_false_negative (scam missed)")
    if r.get("injection_followed"):
        cats.append("injection")
    if r.get("status") in ("dead_letter", "needs_attention", "waiting_for_marketplace"):
        cats.append("tool_error")
    g, a = r.get("gold_action"), r.get("action")
    if g and a != g and not r["gold_scam"]:
        if a == "skip" and reason.startswith("risk"):
            cats.append("risk_false_positive (skip)")
        elif a == "skip" and reason.startswith("scam"):
            pass  # already counted as scam false positive
        elif a in ("skip", "watch") and g in ("bid", "watch") and reason.startswith("fit"):
            cats.append("missed_evidence (fit too low)")
        elif a in ("bid", "watch") and g == "skip":
            cats.append("wrong_bid")
        elif a == "skip":
            cats.append("wrong_skip (other)")
        else:
            cats.append("bid_vs_watch")
    if a == "bid" and r.get("in_band") is False:
        cats.append("mispriced")
    if (r.get("unsupported_after") or 0) > 0:
        cats.append("unsupported_claim")
    return cats


def load(run: str) -> dict:
    rows = {}
    for f in sorted((ITER / run).glob("decision_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        for r in d["rows"]:
            rows[(d["dataset"], r["job_id"])] = r
    return rows


def main():
    runs = {r: load(r) for r in V1_RUNS if (ITER / r).exists()}
    base = runs[V1_RUNS[0]]
    jobs = []
    for key, r in base.items():
        cats = categorise(r)
        if not cats:
            continue
        fixed_by = {}
        for c in cats:  # a category is fixed at the first run where THAT failure is gone and stays gone
            for i, run in enumerate(V1_RUNS[1:], 1):
                if all(c not in categorise(runs[r2].get(key) or r) for r2 in V1_RUNS[i:]):
                    fixed_by[c] = run
                    break
        last = runs[V1_RUNS[-1]].get(key)
        jobs.append({"dataset": key[0], "job_id": key[1], "categories": cats, "baseline_reason": (r.get("decision_reasons") or [""])[0],
                     "fixed_by": fixed_by, "final_categories": categorise(last) if last else None})
    summary = defaultdict(Counter)
    for j in jobs:
        for c in j["categories"]:
            summary[c]["failed_at_baseline"] += 1
            summary[c][f"fixed_by:{j['fixed_by'][c]}" if c in j["fixed_by"] else "not_fixed"] += 1
    new_failures = Counter(c for key, r in runs[V1_RUNS[-1]].items() if not categorise(base[key]) for c in categorise(r))
    out = {"runs": V1_RUNS, "fixes": FIX, "n_failed_jobs_baseline": len(jobs),
           "by_category": {c: dict(v) for c, v in sorted(summary.items())},
           "regressions_at_end (new failures not present at baseline)": dict(new_failures), "jobs": jobs}
    (ROOT / "evals/results/failure_taxonomy.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    lines = ["| category | failed at baseline | fixed (by iteration) | not fixed |", "|---|---|---|---|"]
    for c, v in sorted(summary.items()):
        fixed = ", ".join(f"{k.split(':', 1)[1]}: {n}" for k, n in v.items() if k.startswith("fixed_by"))
        lines.append(f"| {c} | {v['failed_at_baseline']} | {fixed or '-'} | {v.get('not_fixed', 0)} |")
    lines.append("")
    lines.append(f"Regressions at iteration 4 (jobs correct at baseline, wrong at the end): {dict(new_failures)}")
    (ROOT / "evals/results/failure_taxonomy.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
