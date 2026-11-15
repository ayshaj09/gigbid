"""Embedders and rerankers. Open models in every profile (Models section).

* HashingEmbedder       - feature-hashed unigrams+bigrams. Deterministic, no download. TESTS/CI ONLY:
                          it is a lexical model, so V0-vs-V2 comparisons made with it are meaningless.
* OllamaEmbedder        - nomic-embed-text / bge-m3 / qwen3-embedding via Ollama's /api/embed.
* SentenceTransformerEmbedder - any HF embedding model on CPU.
* LexicalReranker       - stemmed-overlap scorer. TESTS/CI ONLY.
* CrossEncoderReranker  - bge-reranker-v2-m3 (or Qwen3-Reranker) via sentence-transformers.
"""
from __future__ import annotations

import hashlib
import os

import numpy as np

from rag.text import overlap, tokens


class HashingEmbedder:
    name = "hashing"

    def __init__(self, dim: int = 512, **_):
        self.dim = dim

    def _vec(self, text: str) -> np.ndarray:
        toks = tokens(text)
        feats = toks + [a + "_" + b for a, b in zip(toks, toks[1:])]
        v = np.zeros(self.dim, dtype=np.float32)
        for f in feats:
            h = int(hashlib.md5(f.encode()).hexdigest(), 16)
            v[h % self.dim] += 1.0 if (h >> 64) & 1 else -1.0
        n = np.linalg.norm(v)
        return v / n if n else v

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.stack([self._vec(t) for t in texts]) if texts else np.zeros((0, self.dim), np.float32)


class OllamaEmbedder:
    name = "ollama"

    def __init__(self, model: str = "nomic-embed-text", **_):
        self.model = model
        self.url = os.environ.get("OLLAMA_URL", "http://localhost:11434") + "/api/embed"

    def embed(self, texts: list[str]) -> np.ndarray:
        import httpx

        resp = httpx.post(self.url, json={"model": self.model, "input": texts}, timeout=120)
        resp.raise_for_status()
        arr = np.asarray(resp.json()["embeddings"], dtype=np.float32)
        return arr / np.linalg.norm(arr, axis=1, keepdims=True).clip(min=1e-9)


class SentenceTransformerEmbedder:
    name = "sentence_transformers"

    def __init__(self, model: str = "BAAI/bge-m3", **_):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model, device="cpu")

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self.model.encode(texts, normalize_embeddings=True), dtype=np.float32)


class LexicalReranker:
    name = "lexical"

    def __init__(self, **_):
        pass

    def score(self, query: str, docs: list[str]) -> list[float]:
        return [overlap(query, d) for d in docs]


class CrossEncoderReranker:
    name = "cross_encoder"

    def __init__(self, model: str = "BAAI/bge-reranker-v2-m3", max_length: int = 256, cache_size: int = 200_000, **_):
        from sentence_transformers import CrossEncoder

        # 256 tokens covers a 180-word chunk plus a requirement; 512 made CPU reranking ~7 s per job.
        self.model = CrossEncoder(model, device="cpu", max_length=max_length)
        self._cache: dict[tuple[str, str], float] = {}  # V3/V4/V8 and ablations rerank the same pairs
        self.cache_size = cache_size

    def score(self, query: str, docs: list[str]) -> list[float]:
        if not docs:
            return []
        todo = [d for d in dict.fromkeys(docs) if (query, d) not in self._cache]
        if todo:
            raw = np.atleast_1d(self.model.predict([(query, d) for d in todo], batch_size=64))
            if len(self._cache) > self.cache_size:
                self._cache.clear()
            for d, x in zip(todo, raw):
                self._cache[(query, d)] = float(1 / (1 + np.exp(-x)))
        return [self._cache[(query, d)] for d in docs]


EMBEDDERS = {"hashing": HashingEmbedder, "ollama": OllamaEmbedder, "sentence_transformers": SentenceTransformerEmbedder}
RERANKERS = {"lexical": LexicalReranker, "cross_encoder": CrossEncoderReranker}


def make_embedder(cfg: dict):
    e = cfg["retrieval"]["embedder"]
    return EMBEDDERS[e["provider"]](model=e.get("model"), dim=e.get("dim", 512))


_RERANKERS: dict = {}


def make_reranker(cfg: dict):
    r = cfg["retrieval"]["reranker"]
    key = (r["provider"], r.get("model"), r.get("max_length", 256))
    if key not in _RERANKERS:
        _RERANKERS[key] = RERANKERS[r["provider"]](model=r.get("model"), max_length=r.get("max_length", 256))
    return _RERANKERS[key]
