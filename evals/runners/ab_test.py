"""X2 extension: pre-registered A/B test of two proposal strategies in GigSim.

    python -m evals.runners.ab_test --dataset <name> --limit 120 --wait-s 180

Arms: A = `writer` (evidence-led opening), B = `writer_b` (question-led opening). Each job is
assigned to one arm by a hash of its id (stable, ~50/50, no peeking). Primary metric: reply
rate; test: two-sided two-proportion z-test, alpha 0.05, plus a bootstrap 95% CI of the
difference. Fill docs/EXTENSION.md (hypothesis, sample size, stopping rule) BEFORE running.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import random
import time

from agent.config import ROOT
from evals.datasets import load
from evals.runners.gigsim_outcomes import _guard, run_arm


def arm_of(job_id: str) -> str:
    return "writer" if int(hashlib.sha256(job_id.encode()).hexdigest(), 16) % 2 == 0 else "writer_b"


def two_proportion_z(s1: int, n1: int, s2: int, n2: int) -> tuple[float, float]:
    p = (s1 + s2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2)) if 0 < p < 1 else float("inf")
    z = (s2 / n2 - s1 / n1) / se if se and se != float("inf") else 0.0
    pval = math.erfc(abs(z) / math.sqrt(2))
    return z, pval


def bootstrap_diff(a: list[int], b: list[int], iters: int = 5000, seed: int = 11) -> tuple[float, float]:
    rng = random.Random(seed)
    diffs = sorted(sum(rng.choices(b, k=len(b))) / len(b) - sum(rng.choices(a, k=len(a))) / len(a) for _ in range(iters))
    return diffs[int(0.025 * iters)], diffs[int(0.975 * iters)]


def required_n_per_arm(p1: float, p2: float, alpha_z: float = 1.96, power_z: float = 0.84) -> int:
    """Sample size per arm for a two-proportion test (80% power, alpha .05)."""
    pbar = (p1 + p2) / 2
    num = (alpha_z * math.sqrt(2 * pbar * (1 - pbar)) + power_z * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
    return math.ceil(num / (p2 - p1) ** 2)


async def main(dataset: str, limit: int, wait_s: int):
    jobs, gold, _ = load(dataset)
    ids = [j for j in gold if j in jobs][:limit]
    arms = {"writer": [j for j in ids if arm_of(j) == "writer"], "writer_b": [j for j in ids if arm_of(j) == "writer_b"]}
    res = {k: await run_arm(dataset, v, k, wait_s) for k, v in arms.items()}
    ya = [int(bool(r.get("replied"))) for r in res["writer"]["rows"] if r.get("proposal_id")]
    yb = [int(bool(r.get("replied"))) for r in res["writer_b"]["rows"] if r.get("proposal_id")]
    z, p = two_proportion_z(sum(ya), len(ya), sum(yb), len(yb)) if ya and yb else (0.0, 1.0)
    lo, hi = bootstrap_diff(ya, yb) if ya and yb else (0.0, 0.0)
    out = {"dataset": dataset, "assignment": "sha256(job_id) % 2", "n": {"A": len(ya), "B": len(yb)},
           "reply_rate": {"A": res["writer"]["reply_rate"], "B": res["writer_b"]["reply_rate"]},
           "z": round(z, 3), "p_value": round(p, 4), "diff_ci95": [round(lo, 4), round(hi, 4)], "arms": res}
    path = ROOT / "evals" / "results" / f"ab_{dataset}_{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "arms"}, indent=1), "\nwrote", path.relative_to(ROOT))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--limit", type=int, default=120)
    ap.add_argument("--wait-s", type=int, default=0)
    ap.add_argument("--power", nargs=2, type=float, metavar=("P_A", "P_B"), help="print n per arm and exit")
    a = ap.parse_args()
    if a.power:
        print("jobs needed per arm:", required_n_per_arm(*a.power))
    else:
        _guard()
        asyncio.run(main(a.dataset, a.limit, a.wait_s))
