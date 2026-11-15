"""Retrieval and decision metrics (B4)."""
from __future__ import annotations

import math


def recall_at_k(ranked: list[str], relevant: set[str], k: int = 5) -> float | None:
    if not relevant:
        return None
    return len(set(ranked[:k]) & relevant) / len(relevant)


def mrr(ranked: list[str], relevant: set[str]) -> float | None:
    if not relevant:
        return None
    for i, r in enumerate(ranked, 1):
        if r in relevant:
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked: list[str], relevant: set[str], k: int = 10) -> float | None:
    if not relevant:
        return None
    dcg = sum(1.0 / math.log2(i + 2) for i, r in enumerate(ranked[:k]) if r in relevant)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(len(relevant), k)))
    return dcg / idcg


def f1(tp: int, fp: int, fn: int) -> float:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return 2 * p * r / (p + r) if p + r else 0.0


def cohen_kappa(a: list, b: list) -> float:
    assert len(a) == len(b) and a
    labels = sorted(set(a) | set(b))
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(lbl) / n) * (b.count(lbl) / n) for lbl in labels)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def percentile(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    if not xs:
        return float("nan")
    idx = min(len(xs) - 1, max(0, math.ceil(p / 100 * len(xs)) - 1))
    return xs[idx]


def weighted_kappa(a: list[int], b: list[int], labels=(1, 2, 3, 4, 5)) -> float:
    """Quadratic-weighted Cohen's kappa for ordinal 1-5 scores (judge calibration)."""
    k = len(labels)
    idx = {lbl: i for i, lbl in enumerate(labels)}
    n = len(a)
    obs = [[0.0] * k for _ in range(k)]
    for x, y in zip(a, b):
        obs[idx[x]][idx[y]] += 1
    ra = [sum(row) for row in obs]
    cb = [sum(obs[i][j] for i in range(k)) for j in range(k)]
    num = den = 0.0
    for i in range(k):
        for j in range(k):
            w = ((i - j) ** 2) / ((k - 1) ** 2)
            num += w * obs[i][j]
            den += w * ra[i] * cb[j] / n
    return 1.0 - num / den if den else 1.0
