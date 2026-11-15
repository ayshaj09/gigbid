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
        persona = json.loads((d / "meta.json").read_text(encoding="utf-8"))["persona"]
    jobs = {j["job_id"]: j for j in json.loads((d / "jobs.json").read_text(encoding="utf-8"))}
    gold = json.loads((d / "gold.json").read_text(encoding="utf-8"))
    return jobs, gold, persona


def is_smoke(name: str, cfg: dict) -> list[str]:
    warnings = []
    if name == "fixtures":
        warnings.append("fixtures dataset: 7 hand-labelled jobs; smoke test only, not reportable")
    else:
        warnings.append("personas, portfolios and client histories are SYNTHETIC; job posts are real (Kaggle); "
                        "see data/market/provenance.json")
        srcs = label_sources(name)
        if any(k.startswith("silver") for f in srcs.values() for k in f):
            warnings.append(f"decision/relevance labels include SILVER rubric labels (not human): {srcs}")
    if cfg["retrieval"]["embedder"]["provider"] == "hashing":
        warnings.append("hashing embedder is lexical; dense-vs-hybrid comparisons are meaningless with it")
    if cfg["retrieval"]["reranker"]["provider"] == "lexical":
        warnings.append("lexical reranker is a test stand-in for a cross-encoder")
    return warnings


def backend_for(name: str):
    """Fixtures run on the fixture marketplace; real dev sets on the simulator built from Kaggle data."""
    from mcp_servers.marketplace.adapters.gigsim import FixtureGigSim

    if name == "fixtures":
        return FixtureGigSim()
    from mcp_servers.marketplace.adapters.local_sim import LocalSim

    return LocalSim()


def label_sources(name: str) -> dict:
    """How many gold labels are human vs silver (rubric), so no silver number is quoted as human."""
    if name == "fixtures":
        return {"action": {"human": "fixtures"}, "relevant": {"human": "fixtures"}}
    gold = json.loads((ROOT / "evals" / "datasets" / name / "gold.json").read_text(encoding="utf-8"))
    out: dict = {"action": {}, "relevant": {}}
    for g in gold.values():
        for f in ("action", "relevant"):
            if g.get(f) is not None:
                src = g.get(f"{f}_source", "unknown")
                out[f][src] = out[f].get(src, 0) + 1
    return out
