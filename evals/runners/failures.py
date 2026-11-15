"""Failure taxonomy (report needs >= 10 failed dev-set jobs, categorised).

    python -m evals.runners.failures --results evals/results/decision_<...>.json
Writes evals/labels/failures_<dataset>.csv with one row per wrong decision/scam call/off-band price
and empty columns for YOUR category and note. Categories (edit if your failures need others):
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

CATEGORIES = ["retrieval_miss", "requirement_decomposition", "fit_threshold", "risk_false_positive",
              "risk_false_negative", "pricing_off_band", "injection_effect", "verification_overreach",
              "critic_loop_no_progress", "compliance_overreach", "tool_or_marketplace_error", "label_disagreement", "other"]


def main(results: str):
    data = json.loads(Path(results).read_text(encoding="utf-8"))
    out = Path("evals/labels") / f"failures_{data['dataset']}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["job_id", "symptom", "gold_action", "action", "gold_scam", "scam", "price", "in_band", "status",
                    "category (" + "|".join(CATEGORIES) + ")", "note"])
        for r in data["rows"]:
            symptoms = []
            if r["gold_action"] and r["action"] != r["gold_action"]:
                symptoms.append(f"decision {r['action']} vs gold {r['gold_action']}")
            if r["scam"] != r["gold_scam"]:
                symptoms.append("scam call wrong")
            if r.get("injection_followed"):
                symptoms.append("planted injection followed")
            if r.get("in_band") is False and r["action"] == "bid":
                symptoms.append("price outside fair band")
            if r.get("status") in ("dead_letter", "needs_attention", "waiting_for_marketplace"):
                symptoms.append(f"run ended {r['status']}")
            if symptoms:
                n += 1
                w.writerow([r["job_id"], "; ".join(symptoms), r["gold_action"], r["action"], r["gold_scam"], r["scam"],
                            r.get("price"), r.get("in_band"), r.get("status"), "", ""])
    print(f"{n} failures -> {out}. Open each job in the UI (Job detail + Run viewer), then fill category and note.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    main(ap.parse_args().results)
