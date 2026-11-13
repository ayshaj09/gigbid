"""Portfolio index: dense vectors + BM25 over chunks, with incremental add (B1).

In-process numpy + rank_bm25 keeps the dev loop and tests dependency-free. For deployment, swap
`dense_search` for a pgvector/Qdrant query; the variants only depend on this class's methods.
"""
from __future__ import annotations

import numpy as np
from rank_bm25 import BM25Okapi

from rag.ingest.loaders import chunk
from rag.text import tokens


class PortfolioIndex:
    def __init__(self, embedder, chunk_cfg: dict | None = None):
        self.embedder = embedder
        self.chunk_cfg = chunk_cfg or {"max_words": 180, "overlap_words": 30}
        self.chunks: list[dict] = []
        self.items: dict[str, dict] = {}
        self.vectors = None
        self._bm25: BM25Okapi | None = None

    # -- building ---------------------------------------------------------------------------
    def add(self, docs: list[dict]) -> int:
        """Add or replace documents. Only new/changed docs are embedded (incremental re-index)."""
        new_chunks = []
        for doc in docs:
            old = self.items.get(doc["evidence_id"])
            if old is not None and old.get("text") == doc.get("text"):
                continue
            if old is not None:
                self.remove(doc["evidence_id"])
            self.items[doc["evidence_id"]] = doc
            new_chunks += chunk(doc, self.chunk_cfg["max_words"], self.chunk_cfg["overlap_words"])
        if new_chunks:
            vecs = self.embedder.embed([self._embed_text(c) for c in new_chunks])
            self.vectors = vecs if self.vectors is None else np.vstack([self.vectors, vecs])
            self.chunks += new_chunks
            self._bm25 = None
        return len(new_chunks)

    def remove(self, evidence_id: str) -> None:
        keep = [i for i, c in enumerate(self.chunks) if c["evidence_id"] != evidence_id]
        self.chunks = [self.chunks[i] for i in keep]
        self.vectors = self.vectors[keep] if self.vectors is not None and keep else None
        self.items.pop(evidence_id, None)
        self._bm25 = None

    @staticmethod
    def _embed_text(c: dict) -> str:
        return f"{c.get('title', '')}. {c['text']} Skills: {', '.join(c.get('skills', []))}"

    # -- search -----------------------------------------------------------------------------
    def _mask(self, filters: dict | None) -> np.ndarray:
        mask = np.ones(len(self.chunks), dtype=bool)
        for key, val in (filters or {}).items():
            vals = set(val) if isinstance(val, (list, tuple, set)) else {val}
            mask &= np.array([c.get(key) in vals for c in self.chunks])
        return mask

    def dense_search(self, query: str, k: int, filters: dict | None = None) -> list[tuple[int, float]]:
        if not self.chunks:
            return []
        q = self.embedder.embed([query])[0]
        sims = self.vectors @ q
        sims[~self._mask(filters)] = -np.inf
        order = np.argsort(-sims)[:k]
        return [(int(i), float(sims[i])) for i in order if np.isfinite(sims[i])]

    def bm25_search(self, query: str, k: int, filters: dict | None = None) -> list[tuple[int, float]]:
        if not self.chunks:
            return []
        if self._bm25 is None:
            self._bm25 = BM25Okapi([c["_tokens"] or ["_"] for c in self.chunks])
        scores = self._bm25.get_scores(tokens(query))
        scores[~self._mask(filters)] = -np.inf
        order = np.argsort(-scores)[:k]
        return [(int(i), float(scores[i])) for i in order if np.isfinite(scores[i]) and scores[i] > 0]
