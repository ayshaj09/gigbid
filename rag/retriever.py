"""Retriever factory: the deployed variant is chosen by config (R6), not hard-coded."""
from __future__ import annotations

import importlib
import json
from pathlib import Path

from rag.index.models import make_embedder, make_reranker
from rag.index.store import PortfolioIndex
from rag.ingest.loaders import load_directory, load_json_items

VARIANTS = ["v0_naive", "v1_decompose", "v2_hybrid", "v3_rerank", "v4_outcome", "v8_corrective"]


def build_index(cfg: dict, sources: list[str | Path], persona: str) -> PortfolioIndex:
    index = PortfolioIndex(make_embedder(cfg), cfg["retrieval"].get("chunk"))
    for src in sources:
        p = Path(src)
        docs = load_json_items(p, persona) if p.suffix == ".json" else load_directory(p, persona)
        index.add(docs)
    return index


def make_pipeline(cfg: dict, index: PortfolioIndex, variant: str | None = None, grader=None):
    name = variant or cfg["retrieval"]["variant"]
    module = importlib.import_module(f"rag.variants.{name}")
    reranker = make_reranker(cfg) if module.FLAGS.rerank else None
    return module.build(index, cfg, reranker=reranker, grader=grader)


def persona_sources(persona: str) -> list[Path]:
    """Where a persona's corpus lives. Instructor corpora go in data/personas/<persona>/."""
    import os

    root = Path(__file__).resolve().parent.parent / "data"
    real = root / "personas" / persona
    if os.environ.get("GIGBID_PERSONA_SOURCE") != "fixtures":
        if (real / "portfolio.json").exists():
            return [real / "portfolio.json"]
        if real.exists():
            return [real]
    fixture = root / "fixtures" / f"portfolio_{persona}.json"
    if fixture.exists():
        return [fixture]
    raise FileNotFoundError(f"no corpus for persona {persona}")


def load_persona(persona: str) -> dict:
    import os

    root = Path(__file__).resolve().parent.parent / "data"
    cands = [root / "personas" / persona / "persona.json", root / "fixtures" / f"persona_{persona}.json"]
    if os.environ.get("GIGBID_PERSONA_SOURCE") == "fixtures":
        cands.reverse()
    for p in cands:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    raise FileNotFoundError(persona)
