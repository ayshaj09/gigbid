"""Relevance-labelling sheet by POOLING (as in TREC): for each sampled dev job, the union of the top-5
evidence items from several retrieval variants. You mark which are relevant; unjudged items count
as not relevant. Pooling from several variants keeps the labels from favouring any one of them.

    python -m datapipe.pool --persona ai_engineer --n 30
    -> evals/datasets/dev_ai_engineer/label_relevance.csv   (fill the `relevant (y/n)` column)
"""
from __future__ import annotations

import argparse
import csv
import json

from agent.config import ROOT, load_config
from agent.nodes.analyst import extract_requirements
from rag.pipeline import RetrievalQuery
from rag.retriever import build_index, make_pipeline, persona_sources

POOL_VARIANTS = ["v0_naive", "v2_hybrid", "v3_rerank", "v4_outcome"]


def main(persona: str, n: int, k: int = 5):
    cfg = load_config()
    d = ROOT / "evals" / "datasets" / f"dev_{persona}"
    jobs = json.loads((d / "jobs.json").read_text(encoding="utf-8"))
    jobs = [j for j in jobs if j.get("source") != "fake_job_postings" and not j.get("planted_injection")][:n]
    index = build_index(cfg, persona_sources(persona), persona)
    pipes = [make_pipeline(cfg, index, v) for v in POOL_VARIANTS]
    rows = 0
    with open(d / "label_relevance.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["job_id", "evidence_id", "relevant (y/n)", "job_title", "job_description", "evidence_title", "evidence_text"])
        for j in jobs:
            reqs = [{"id": r.id, "text": r.text, "skills": r.skills} for r in extract_requirements(j)]
            q = RetrievalQuery(text=f"{j['title']}. {j['description']}", requirements=reqs)
            pooled = list(dict.fromkeys(i.evidence_id for p in pipes for i in p.retrieve(q, k).items))
            for eid in sorted(pooled):  # sorted, so the sheet does not reveal any variant's ranking
                it = index.items[eid]
                w.writerow([j["job_id"], eid, "", j["title"], j["description"][:400], it["title"], it["text"][:400]])
                rows += 1
    print(f"{rows} rows for {len(jobs)} jobs -> {d / 'label_relevance.csv'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", required=True)
    ap.add_argument("--n", type=int, default=30)
    a = ap.parse_args()
    main(a.persona, a.n)
