"""LLM-as-judge with a rubric, and its calibration against your own labels (B4).

  1) export   python -m evals.runners.judge export --results evals/results/decision_<...>.json --n 30
              -> evals/labels/judge_labels.csv ; fill the human_* columns yourself (1-5), BLIND to the judge
  2) calibrate python -m evals.runners.judge calibrate --labels evals/labels/judge_labels.csv
              -> quadratic-weighted kappa + exact / within-1 agreement per criterion
  3) score    python -m evals.runners.judge score --results evals/results/decision_<...>.json
Only cite judge scores in the report if calibration kappa is acceptable (say >= 0.6), and say so.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import random
import time
from pathlib import Path

from pydantic import BaseModel, Field

from agent.config import ROOT, load_config
from agent.guardrails import delimit_untrusted
from agent.llm import LLMRouter
from evals.datasets import load
from rag.metrics import weighted_kappa

CRITERIA = ["grounding", "specificity", "persuasiveness", "professionalism", "overall"]


class JudgeScore(BaseModel):
    grounding: int = Field(ge=1, le=5)
    specificity: int = Field(ge=1, le=5)
    persuasiveness: int = Field(ge=1, le=5)
    professionalism: int = Field(ge=1, le=5)
    overall: int = Field(ge=1, le=5)
    rationale: str = ""


async def judge_one(router: LLMRouter, job: dict, evidence_text: str, letter: str) -> JudgeScore:
    score, _ = await router.structured("judge", "judge", JudgeScore,
                                       job_post=delimit_untrusted(f"{job['title']}\n\n{job['description']}"),
                                       evidence=evidence_text, proposal=letter)
    return score


def _evidence_text(persona: str, ids: list[str]) -> str:
    from rag.retriever import build_index, persona_sources

    idx = build_index(load_config(), persona_sources(persona), persona)
    return "\n".join(f"[{i}] {idx.items[i]['title']}: {idx.items[i]['text']}" for i in ids if i in idx.items)


def export(results: str, n: int, out: str):
    data = json.loads(Path(results).read_text(encoding="utf-8"))
    rows = [r for r in data["rows"] if r.get("letter")]
    random.Random(7).shuffle(rows)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["dataset", "job_id", "letter", "evidence_ids"] + [f"human_{c}" for c in CRITERIA])
        for r in rows[:n]:
            w.writerow([data["dataset"], r["job_id"], r["letter"], " ".join(r.get("evidence_ids", []))] + [""] * len(CRITERIA))
    print(f"wrote {out}: label {min(n, len(rows))} proposals (1-5 each) WITHOUT looking at judge scores")


async def calibrate(labels: str):
    cfg = load_config()
    router = LLMRouter(cfg)
    rows = list(csv.DictReader(open(labels, encoding="utf-8")))
    human, model = {c: [] for c in CRITERIA}, {c: [] for c in CRITERIA}
    cache: dict = {}
    for r in rows:
        if not r["human_overall"]:
            continue
        if r["dataset"] not in cache:
            cache[r["dataset"]] = load(r["dataset"])
        jobs, _, persona = cache[r["dataset"]]
        s = await judge_one(router, jobs[r["job_id"]], _evidence_text(persona, r["evidence_ids"].split()), r["letter"])
        for c in CRITERIA:
            human[c].append(int(r[f"human_{c}"]))
            model[c].append(getattr(s, c))
    out = {c: {"n": len(human[c]), "weighted_kappa": round(weighted_kappa(human[c], model[c]), 3),
               "exact": round(sum(a == b for a, b in zip(human[c], model[c])) / len(human[c]), 3),
               "within_1": round(sum(abs(a - b) <= 1 for a, b in zip(human[c], model[c])) / len(human[c]), 3)}
           for c in CRITERIA if human[c]}
    path = ROOT / "evals" / "results" / f"judge_calibration_{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps({"labels": labels, "judge_model": router.model_for("judge"), "agreement": out}, indent=1))
    print(json.dumps(out, indent=1), "\nwrote", path.relative_to(ROOT))


async def score(results: str):
    data = json.loads(Path(results).read_text(encoding="utf-8"))
    jobs, _, persona = load(data["dataset"])
    router = LLMRouter(load_config())
    scores = []
    for r in data["rows"]:
        if r.get("letter"):
            s = await judge_one(router, jobs[r["job_id"]], _evidence_text(persona, r.get("evidence_ids", [])), r["letter"])
            scores.append({"job_id": r["job_id"], **s.model_dump()})
    mean = {c: round(sum(s[c] for s in scores) / len(scores), 3) for c in CRITERIA} if scores else {}
    path = ROOT / "evals" / "results" / f"judge_{data['dataset']}_{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps({"source": results, "mean": mean, "scores": scores}, indent=1), encoding="utf-8")
    print(json.dumps(mean, indent=1), "\nwrote", path.relative_to(ROOT))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--results", required=True)
    e.add_argument("--n", type=int, default=30)
    e.add_argument("--out", default="evals/labels/judge_labels.csv")
    c = sub.add_parser("calibrate")
    c.add_argument("--labels", default="evals/labels/judge_labels.csv")
    s = sub.add_parser("score")
    s.add_argument("--results", required=True)
    a = ap.parse_args()
    if a.cmd == "export":
        export(a.results, a.n, a.out)
    elif a.cmd == "calibrate":
        asyncio.run(calibrate(a.labels))
    else:
        asyncio.run(score(a.results))
