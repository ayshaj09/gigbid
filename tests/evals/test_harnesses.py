"""Plumbing smoke tests for the experiment harnesses (scripted fake model; no real numbers)."""
import json

from agent.config import ROOT
from evals.runners import tool_granularity as tg


async def test_tool_granularity_plumbing(monkeypatch, tmp_path):
    tasks = json.loads((ROOT / "evals/datasets/tool_tasks.json").read_text(encoding="utf-8"))
    assert len(tasks) == 40
    monkeypatch.setattr(tg, "ROOT", tmp_path)
    (tmp_path / "evals" / "results").mkdir(parents=True)
    (tmp_path / "evals" / "datasets").mkdir(parents=True)
    (tmp_path / "evals/datasets/tool_tasks.json").write_text(json.dumps(tasks[:6]), encoding="utf-8")
    summary, _ = await tg.main("evals/datasets/tool_tasks.json", ["fine"], model=tg.scripted_model_for(tasks[:6]))
    assert summary["fine"]["tool_accuracy"] == 1.0 and summary["fine"]["n"] == 6


def test_every_task_tool_exists():
    snaps = {t["name"] for s in ("portfolio", "marketplace", "workspace")
             for t in json.loads((ROOT / f"tests/contract/snapshots/{s}.json").read_text(encoding="utf-8"))}
    tasks = json.loads((ROOT / "evals/datasets/tool_tasks.json").read_text(encoding="utf-8"))
    assert {t["tool"] for t in tasks} <= snaps


def test_ab_statistics():
    from evals.runners.ab_test import arm_of, bootstrap_diff, required_n_per_arm, two_proportion_z

    assert {arm_of(f"J-{i}") for i in range(20)} == {"writer", "writer_b"}
    z, p = two_proportion_z(10, 100, 25, 100)
    assert z > 2.5 and p < 0.01
    lo, hi = bootstrap_diff([0] * 90 + [1] * 10, [0] * 75 + [1] * 25)
    assert 0 < lo < hi
    assert 190 < required_n_per_arm(0.10, 0.20) < 210


def test_weighted_kappa():
    from rag.metrics import weighted_kappa

    assert weighted_kappa([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) == 1.0
    assert weighted_kappa([1, 2, 3, 4, 5], [2, 3, 4, 5, 5]) > 0.6


async def test_strategy_b_opens_with_question(tmp_path):
    from agent.testing import harness

    async with harness(tmp_path, cfg_overrides={"writer": {"strategy": "writer_b"}}) as r:
        res = await r.start_job("J-104")
        assert res.interrupt["draft"]["cover_letter"].startswith("Quick question")


def test_outcomes_refuse_without_real_gigsim(monkeypatch):
    import pytest

    from evals.runners.gigsim_outcomes import _guard

    monkeypatch.setenv("GIGSIM_BASE_URL", "fixture://")
    with pytest.raises(SystemExit):
        _guard()
