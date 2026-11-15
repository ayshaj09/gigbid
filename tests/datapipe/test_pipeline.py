"""Data pipeline on schema-faithful MOCK raw files (dev/make_mock_raw.py): structure, provenance,
synthetic flags, dedupe, label merge, and the simulator's reply model."""
import csv
import json

import pytest

import datapipe.build as B
import datapipe.load as L
from dev.make_mock_raw import main as make_mock


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    raw = tmp_path_factory.mktemp("raw")
    root = tmp_path_factory.mktemp("root")
    make_mock(str(raw), n=900)
    mp = pytest.MonkeyPatch()
    mp.setattr(L, "RAW", raw)
    mp.setattr(B, "ROOT", root)
    B.build(60000, 300, 60)
    yield root
    mp.undo()


def test_outputs_and_provenance(built):
    jobs = json.loads((built / "data/market/jobs.json").read_text(encoding="utf-8"))
    prov = json.loads((built / "data/market/provenance.json").read_text(encoding="utf-8"))
    assert jobs and prov["jobs_after_dedupe"] <= sum(prov["raw_rows_read"].values())
    assert all(j["source"] for j in jobs)                                  # every job knows its source
    title_only = [j for j in jobs if j["source"] in ("upwork_jobs_2024_50k", "upwork_jobs_200k")]
    assert title_only and all("description" in j["synthetic_fields"] for j in title_only)
    assert any("description" not in j["synthetic_fields"] for j in jobs if j["source"] == "upwork_jobs_60k")
    assert len({j["job_id"] for j in jobs}) == len(jobs)


def test_synthetic_records_are_flagged(built):
    for p in ("ai_engineer", "web_fullstack", "data_analyst"):
        persona = json.loads((built / f"data/personas/{p}/persona.json").read_text(encoding="utf-8"))
        items = json.loads((built / f"data/personas/{p}/portfolio.json").read_text(encoding="utf-8"))
        assert persona["synthetic"] and all(i["synthetic"] and i["source"].startswith("synthetic/") for i in items)
        assert {"case_study", "review", "past_proposal", "cv"} <= {i["type"] for i in items}
    clients = json.loads((built / "data/market/clients.json").read_text(encoding="utf-8"))
    assert all(c["synthetic"] for c in clients.values())


def test_dev_set_labels_and_scam_ground_truth(built):
    d = built / "evals/datasets/dev_ai_engineer"
    jobs = json.loads((d / "jobs.json").read_text(encoding="utf-8"))
    gold = json.loads((d / "gold.json").read_text(encoding="utf-8"))
    assert all(g["action"] is None for g in gold.values())               # no invented decision labels
    fakes = [j for j in jobs if j["source"] == "fake_job_postings"]
    assert fakes and all(gold[j["job_id"]]["scam_source"] == "dataset label `fraudulent`" for j in fakes)
    assert any(j.get("planted_injection") for j in jobs)
    # scam and legit postings get clients from the same distribution (no leaked signal)
    clients = json.loads((built / "data/market/clients.json").read_text(encoding="utf-8"))
    scam_clients = [clients[j["client_id"]] for j in fakes if j["label_scam"]]
    assert scam_clients and any(c["hires"] > 0 for c in scam_clients)   # not all made to look suspicious


def test_apply_labels(built, monkeypatch):
    import datapipe.apply_labels as A

    monkeypatch.setattr(A, "ROOT", built)
    d = built / "evals/datasets/dev_ai_engineer"
    rows = list(csv.reader(open(d / "label_decisions.csv", encoding="utf-8")))
    rows[1][1] = "bid"
    csv.writer(open(d / "label_decisions.csv", "w", newline="", encoding="utf-8")).writerows(rows)
    A.main("ai_engineer")
    gold = json.loads((d / "gold.json").read_text(encoding="utf-8"))
    assert gold[rows[1][0]]["action"] == "bid"


def test_reply_model_prefers_specific_over_generic():
    from mcp_servers.marketplace.adapters.local_sim import reply_probability

    job = {"title": "Celery task queue for nightly ETL", "description": "Our nightly ETL on cron fails silently; we need Celery, Redis retries and monitoring.",
           "required_skills": ["Celery", "Redis"], "budget": {"min": 40, "max": 60, "type": "hourly"}}
    client = {"payment_verified": True, "hires": 10, "jobs_posted": 12, "average_rating": 4.8, "total_spent_usd": 20000}
    good, _ = reply_probability(job, client, "Your nightly ETL fails silently on cron. I replaced cron with Celery and Redis retries plus monitoring.", 50)
    generic, _ = reply_probability(job, client, "Hi, I am a passionate freelancer with many years of experience. I have read your job post.", 50)
    pricey, _ = reply_probability(job, client, "Your nightly ETL fails silently on cron. I replaced cron with Celery and Redis retries plus monitoring.", 200)
    assert generic < 0.06 < good < 0.6 and pricey < good
