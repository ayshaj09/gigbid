"""Merge your filled labelling sheets into gold.json. Only labelled rows become gold; the eval
runners ignore jobs whose `action` / `relevant` is still null.

    python -m datapipe.apply_labels --persona ai_engineer
"""
from __future__ import annotations

import argparse
import csv
import json

from agent.config import ROOT


def main(persona: str):
    d = ROOT / "evals" / "datasets" / f"dev_{persona}"
    gold = json.loads((d / "gold.json").read_text(encoding="utf-8"))
    n_dec = n_rel = 0
    if (d / "label_decisions.csv").exists():
        for row in csv.DictReader(open(d / "label_decisions.csv", encoding="utf-8")):
            a = (row.get("action (bid/watch/skip)") or "").strip().lower()
            if a in ("bid", "watch", "skip") and row["job_id"] in gold:
                gold[row["job_id"]]["action"] = a
                gold[row["job_id"]]["action_source"] = "human"
                n_dec += 1
    if (d / "label_relevance.csv").exists():
        judged: dict[str, list[str]] = {}
        for row in csv.DictReader(open(d / "label_relevance.csv", encoding="utf-8")):
            v = (row.get("relevant (y/n)") or "").strip().lower()
            if v in ("y", "n", "yes", "no", "1", "0"):
                judged.setdefault(row["job_id"], [])
                if v in ("y", "yes", "1"):
                    judged[row["job_id"]].append(row["evidence_id"])
        for jid, rel in judged.items():
            if jid in gold:
                gold[jid]["relevant"] = rel
                gold[jid]["relevant_source"] = "human"
                n_rel += 1
    (d / "gold.json").write_text(json.dumps(gold, indent=1), encoding="utf-8")
    print(f"{persona}: {n_dec} decision labels, {n_rel} jobs with relevance judgements -> gold.json")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", required=True)
    main(ap.parse_args().persona)
