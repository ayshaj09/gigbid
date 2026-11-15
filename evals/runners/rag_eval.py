"""B4 retrieval metrics for every variant (and ablations), per persona and job type.

    python -m evals.runners.rag_eval --dataset fixtures --variants all
    python -m evals.runners.rag_eval --dataset dev_ai_engineer --ablate v8_corrective
Writes evals/results/rag_<dataset>_<timestamp>.json; every number in the report must cite one.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import statistics
import time

from agent.config import ROOT, load_config
from agent.nodes.analyst import extract_requirements
from evals.datasets import is_smoke, label_sources, load
from rag.index.models import make_reranker
from rag.metrics import mrr, ndcg_at_k, recall_at_k
from rag.pipeline import Flags, Pipeline, RetrievalQuery
from rag.retriever import VARIANTS, build_index, make_pipeline, persona_sources


def evaluate(pipe, jobs, gold) -> dict:
    rows = []
    for jid, g in gold.items():
        rel = set(g.get("relevant") or [])
        if not rel or jid not in jobs:
            continue
        job = jobs[jid]
        reqs = [{"id": r.id, "text": r.text, "skills": r.skills} for r in extract_requirements(job)]
        t0 = time.perf_counter()
        res = pipe.retrieve(RetrievalQuery(text=f"{job['title']}. {job['description']}", requirements=reqs), k=10)
        dt = time.perf_counter() - t0
        ranked = [i.evidence_id for i in res.items]
        rows.append({"job_id": jid, "category": job.get("category", "other"), "n_requirements": len(reqs),
                     "recall@5": recall_at_k(ranked, rel, 5), "mrr": mrr(ranked, rel),
                     "ndcg@10": ndcg_at_k(ranked, rel, 10), "latency_s": dt, "ranked": ranked[:10]})

    def agg(rs):
        return {m: round(statistics.mean(r[m] for r in rs), 4) for m in ("recall@5", "mrr", "ndcg@10")} | {
            "n": len(rs), "p95_latency_s": round(sorted(r["latency_s"] for r in rs)[max(0, int(0.95 * len(rs)) - 1)], 4)}

    by_cat = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)
    many = [r for r in rows if r["n_requirements"] >= 4]
    return {"overall": agg(rows) if rows else {}, "by_category": {c: agg(v) for c, v in by_cat.items()},
            "jobs_with_4plus_requirements": agg(many) if many else {}, "rows": rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="fixtures")
    ap.add_argument("--variants", default="all")
    ap.add_argument("--ablate", default=None, help="variant to ablate one component at a time")
    args = ap.parse_args()
    cfg = load_config()
    jobs, gold, persona = load(args.dataset)
    index = build_index(cfg, persona_sources(persona), persona)
    results = {}
    names = VARIANTS if args.variants == "all" else args.variants.split(",")
    for v in names:
        results[v] = evaluate(make_pipeline(cfg, index, v), jobs, gold)
    if args.ablate:
        import importlib

        base = importlib.import_module(f"rag.variants.{args.ablate}").FLAGS
        for f in dataclasses.fields(Flags):
            if getattr(base, f.name):
                flags = dataclasses.replace(base, **{f.name: False})
                pipe = Pipeline(index, cfg, flags, reranker=make_reranker(cfg) if flags.rerank else None)
                results[f"{args.ablate}-minus-{f.name}"] = evaluate(pipe, jobs, gold)
    out = {"dataset": args.dataset, "persona": persona, "embedder": cfg["retrieval"]["embedder"],
           "reranker": cfg["retrieval"]["reranker"], "warnings": is_smoke(args.dataset, cfg), "label_sources": label_sources(args.dataset),
           "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "results": results}
    path = ROOT / "evals" / "results" / f"rag_{args.dataset}_{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"{'variant':32} {'R@5':>6} {'MRR':>6} {'nDCG@10':>8}")
    for v, r in results.items():
        o = r["overall"]
        print(f"{v:32} {o.get('recall@5', 0):6.3f} {o.get('mrr', 0):6.3f} {o.get('ndcg@10', 0):8.3f}")
    for w in out["warnings"]:
        print("WARNING:", w)
    print("wrote", path.relative_to(ROOT))


if __name__ == "__main__":
    main()
