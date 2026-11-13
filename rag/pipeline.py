"""Composable retrieval pipeline. Each variant in rag/variants/ is a set of flags over this one
implementation, so the ablation ("best minus one component") is a flag flip, not new code.

    decompose      V1  one retrieval per extracted requirement, merged by RRF
    hybrid         V2  BM25 + dense fused with reciprocal rank fusion
    rerank         V3  cross-encoder rerank of the fused candidates
    outcome_aware  V4  boost items/phrasing from proposals that won or got replies
    corrective     V8  grade evidence per requirement, re-query once when weak, refuse when none

Results are aggregated from chunks to evidence items (max chunk score per item), because the
gold labels, the Writer and the claim verifier all work at the evidence-item level.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from agent.handoffs import EvidenceItem
from rag.text import overlap, tokens


@dataclass(frozen=True)
class Flags:
    decompose: bool = False
    hybrid: bool = False
    rerank: bool = False
    outcome_aware: bool = False
    corrective: bool = False


@dataclass
class RetrievalQuery:
    text: str                                  # the whole job post (V0 uses only this)
    requirements: list[dict] = field(default_factory=list)  # [{"id","text","skills"}]
    filters: dict | None = None


@dataclass
class RetrievalResult:
    items: list[EvidenceItem]
    per_requirement: dict[str, list[tuple[str, float]]] = field(default_factory=dict)
    weak_requirements: list[str] = field(default_factory=list)
    requeries: list[dict] = field(default_factory=list)


def rrf(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    out: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            out[idx] = out.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return out


class Pipeline:
    def __init__(self, index, cfg: dict, flags: Flags, reranker=None, grader=None):
        self.index = index
        self.rcfg = cfg["retrieval"]
        self.flags = flags
        self.reranker = reranker
        self.grader = grader  # optional async-free callable(requirement, docs)->(score, requery|None)

    # ---- one query -> ranked chunk indices with scores ------------------------------------
    def _candidates(self, query: str, n: int, filters) -> list[tuple[int, float]]:
        dense = self.index.dense_search(query, n, filters)
        if not self.flags.hybrid:
            return dense
        sparse = self.index.bm25_search(query, n, filters)
        fused = rrf([[i for i, _ in dense], [i for i, _ in sparse]], self.rcfg.get("rrf_k", 60))
        return sorted(fused.items(), key=lambda x: -x[1])[:n]

    def _rank(self, query: str, n: int, filters) -> list[tuple[int, float]]:
        cands = self._candidates(query, max(n, 20) if self.flags.rerank else n, filters)
        if self.flags.rerank and self.reranker and cands:
            docs = [self.index._embed_text(self.index.chunks[i]) for i, _ in cands]
            scores = self.reranker.score(query, docs)
            cands = sorted(zip([i for i, _ in cands], scores), key=lambda x: -x[1])
        if self.flags.outcome_aware:
            boost = self.rcfg.get("outcome_boost", {})
            cands = sorted(((i, s + boost.get(self.index.chunks[i].get("outcome") or "", 0.0) * max(abs(s), 1e-3))
                            for i, s in cands), key=lambda x: -x[1])
        return cands[:n]

    def _to_items(self, ranked: list[tuple[int, float]]) -> list[tuple[str, float]]:
        best: dict[str, float] = {}
        for i, s in ranked:
            eid = self.index.chunks[i]["evidence_id"]
            best[eid] = max(best.get(eid, float("-inf")), s)
        return sorted(best.items(), key=lambda x: -x[1])

    # ---- corrective grading (V8) ---------------------------------------------------------
    def _grade(self, req_text: str, eids: list[str]) -> tuple[float, str | None]:
        docs = [self.index.items[e]["text"] for e in eids[:3]]
        if self.grader:
            return self.grader(req_text, docs)
        score = max((overlap(req_text, d + " " + " ".join(self.index.items[e].get("skills", [])))
                     for d, e in zip(docs, eids)), default=0.0)
        return score, None

    # ---- public --------------------------------------------------------------------------
    def retrieve(self, q: RetrievalQuery, k: int | None = None) -> RetrievalResult:
        k = k or self.rcfg.get("k", 8)
        per_req: dict[str, list[tuple[str, float]]] = {}
        weak, requeries = [], []
        if self.flags.decompose and q.requirements:
            rankings = []
            for req in q.requirements:
                rtext = req["text"] + " " + " ".join(req.get("skills", []))
                items = self._to_items(self._rank(rtext, k * 2, q.filters))
                if self.flags.corrective:
                    grade, requery = self._grade(rtext, [e for e, _ in items])
                    cfg = self.rcfg.get("corrective", {})
                    if grade < cfg.get("min_grade", 0.35) and cfg.get("max_requeries", 1) > 0:
                        requery = requery or " ".join(dict.fromkeys(tokens(rtext) + req.get("skills", [])))
                        items2 = self._to_items(self._rank(requery, k * 2, q.filters))
                        grade2, _ = self._grade(rtext, [e for e, _ in items2])
                        requeries.append({"requirement": req["id"], "query": requery, "grade_before": grade,
                                          "grade_after": grade2})
                        if grade2 > grade:
                            items, grade = items2, grade2
                    if grade < cfg.get("min_grade", 0.35):
                        weak.append(req["id"])
                        items = []  # refuse to claim: no evidence passed to the writer for this requirement
                per_req[req["id"]] = items[:k]
                rankings.append([e for e, _ in items[:k * 2]])
            fused: dict[str, float] = {}
            for ranking in rankings:
                for rank, eid in enumerate(ranking):
                    fused[eid] = fused.get(eid, 0.0) + 1.0 / (self.rcfg.get("rrf_k", 60) + rank + 1)
            ranked_items = sorted(fused.items(), key=lambda x: -x[1])
        else:
            ranked_items = self._to_items(self._rank(q.text, k * 3, q.filters))
        items = []
        for eid, score in ranked_items[:k]:
            doc = self.index.items[eid]
            items.append(EvidenceItem(evidence_id=eid, type=doc["type"], title=doc.get("title", ""),
                                      text=doc["text"], source=doc.get("source", ""), date=doc.get("date"),
                                      outcome=doc.get("outcome"), skills=doc.get("skills", []), score=float(score)))
        return RetrievalResult(items=items, per_requirement=per_req, weak_requirements=weak, requeries=requeries)
