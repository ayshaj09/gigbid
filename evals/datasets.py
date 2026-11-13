"""Dataset loading for the eval runners.

A dataset is a directory with `jobs.json` (list of job posts in the GigSim shape) and
`gold.json` ({job_id: {action, scam, relevant: [evidence_id], fair_band: [lo, hi]}}), plus the
persona name whose corpus the evidence ids refer to. When the instructor's dev set arrives, write
a converter into this shape (or extend `load`); the runners do not change.

`fixtures` is the tiny hand-made set in data/fixtures: a smoke test, NOT a result.
"""
from __future__ import annotations

import json

from agent.config import ROOT


def load(name: str) -> tuple[dict, dict, str]:
    if name == "fixtures":
        d = ROOT / "data" / "fixtures"
        persona = "ai_engineer"
    else:
        d = ROOT / "evals" / "datasets" / name
        persona = json.loads((d / "meta.json").read_text())["persona"]
    jobs = {j["job_id"]: j for j in json.loads((d / "jobs.json").read_text())}
    gold = json.loads((d / "gold.json").read_text())
    return jobs, gold, persona


def is_smoke(name: str, cfg: dict) -> list[str]:
    warnings = []
    if name == "fixtures":
        warnings.append("fixtures dataset: 7 hand-labelled jobs; smoke test only, not reportable")
    if cfg["retrieval"]["embedder"]["provider"] == "hashing":
        warnings.append("hashing embedder is lexical; dense-vs-hybrid comparisons are meaningless with it")
    if cfg["retrieval"]["reranker"]["provider"] == "lexical":
        warnings.append("lexical reranker is a test stand-in for a cross-encoder")
    return warnings
