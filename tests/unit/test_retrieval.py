import json

import pytest

from agent.config import ROOT
from rag.metrics import cohen_kappa, mrr, ndcg_at_k, recall_at_k
from rag.pipeline import RetrievalQuery
from rag.retriever import VARIANTS, build_index, make_pipeline


@pytest.fixture(scope="module")
def index():
    from agent.config import load_config

    return build_index(load_config(), [ROOT / "data/fixtures/portfolio_ai_engineer.json"], "ai_engineer")


@pytest.mark.parametrize("variant", VARIANTS)
def test_every_variant_runs_and_finds_celery(index, variant):
    from agent.config import load_config

    p = make_pipeline(load_config(), index, variant)
    q = RetrievalQuery(text="Move cron ETL to Celery with Redis retries",
                       requirements=[{"id": "r1", "text": "Celery with Redis and retries", "skills": ["Celery"]}])
    ids = [i.evidence_id for i in p.retrieve(q, 5).items]
    assert "cs-celery-etl" in ids


def test_corrective_refuses_when_no_evidence(index):
    from agent.config import load_config

    p = make_pipeline(load_config(), index, "v8_corrective")
    q = RetrievalQuery(text="iOS", requirements=[{"id": "r1", "text": "SwiftUI Core Data App Store release", "skills": []}])
    res = p.retrieve(q, 5)
    assert res.weak_requirements == ["r1"] and res.per_requirement["r1"] == []


def test_incremental_reindex(index):
    n = index.add([{"evidence_id": "new-1", "type": "case_study", "title": "Kafka streaming", "text": "Built Kafka consumers.",
                    "skills": ["Kafka"], "persona": "ai_engineer"}])
    assert n == 1 and index.add([index.items["new-1"]]) == 0  # unchanged doc is not re-embedded
    index.remove("new-1")


def test_metrics():
    assert recall_at_k(["a", "b", "c"], {"a", "z"}, 5) == 0.5
    assert mrr(["x", "a"], {"a"}) == 0.5
    assert ndcg_at_k(["a"], {"a"}) == 1.0
    assert cohen_kappa([1, 0, 1, 0], [1, 0, 1, 0]) == 1.0


def test_gold_file_is_consistent():
    gold = json.loads((ROOT / "data/fixtures/gold.json").read_text())
    items = {i["evidence_id"] for i in json.loads((ROOT / "data/fixtures/portfolio_ai_engineer.json").read_text())}
    assert all(set(g["relevant"]) <= items for g in gold.values())
