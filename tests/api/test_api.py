"""API end to end: register -> onboard -> scout -> analyse (SSE) -> detail -> approve -> analytics."""
import json
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    for k, v in {"APP_DB": tmp_path / "app.sqlite", "GIGBID_SQLITE": tmp_path / "ckpt.sqlite",
                 "GIGBID_DATA_DIR": tmp_path, "MODEL_PROFILE": "offline", "GIGSIM_BASE_URL": "fixture://",
                 "MARKETPLACE_RPM": "6000", "DATABASE_URL": "", "MCP_MODE": "inprocess"}.items():
        monkeypatch.setenv(k, str(v))
    from apps.api.main import app

    with TestClient(app) as c:
        yield c


def auth(c, email="alice@example.com"):
    r = c.post("/auth/register", json={"email": email, "password": "correct horse"})
    assert r.status_code == 200
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    assert c.post("/onboarding", headers=h, json={"persona_id": "ai_engineer", "hourly_rate_usd": 40, "floor_usd": 300,
                                                 "weekly_connects_budget": 80, "saved_searches": ["python machine learning"]}).status_code == 200
    return h


def wait_run(c, h, run_id, timeout=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = c.get(f"/runs/{run_id}", headers=h).json()
        if r["status"] != "running":
            return r
        time.sleep(0.05)
    raise TimeoutError(run_id)


def test_requires_auth(client):
    assert client.get("/jobs").status_code == 401
    assert client.get("/jobs", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_login_and_wrong_password(client):
    auth(client)
    assert client.post("/auth/login", json={"email": "alice@example.com", "password": "wrong password"}).status_code == 401
    r = client.post("/auth/login", json={"email": "alice@example.com", "password": "correct horse"})
    assert r.json()["onboarded"] is True


def test_full_flow(client):
    h = auth(client)
    run = client.post("/jobs/J-104/analyze", headers=h).json()
    # live progress over SSE
    with client.stream("GET", run["events_url"], headers=h) as s:
        nodes = [json.loads(line[5:])["node"] for line in s.iter_lines() if line.startswith("data:")]
    assert {"scout", "fit_matcher", "writer", "critic", "__end__"} <= set(nodes)
    inbox = client.get("/jobs", headers=h).json()
    assert inbox[0]["job_id"] == "J-104" and inbox[0]["status"] == "awaiting_approval"
    d = client.get("/jobs/J-104", headers=h).json()
    assert d["pending_approval"]["kind"] == "proposal" and d["fit_report"]["matrix"]
    assert [a["target_id"] for a in client.get("/approvals", headers=h).json()] == ["J-104"]
    r = client.post("/approvals/jobs/J-104", headers=h, json={"action": "approve"}).json()
    assert wait_run(client, h, r["run_id"])["status"] == "submitted"
    assert client.post("/approvals/jobs/J-104", headers=h, json={"action": "approve"}).status_code == 409
    client.post("/jobs/J-104/outcome", headers=h, json={"outcome": "replied"})
    a = client.get("/analytics", headers=h).json()
    assert a["bids_submitted"] == 1 and a["connects_spent"] == 10 and a["approvals"]["approve"] == 1
    assert a["reply_rate"] == 1.0


def test_scout_dedupes_and_skips_scam(client):
    h = auth(client)
    runs = client.post("/jobs/scout", headers=h, json={"queries": ["dashboard", "dashboard"]}).json()
    assert len(runs) == len({r["target_id"] for r in runs})
    for r in runs:
        wait_run(client, h, r["run_id"])
    scam = [j for j in client.get("/jobs", headers=h).json() if j["job_id"] == "J-101"]
    assert scam and scam[0]["is_scam"] and scam[0]["status"] == "skipped"
    assert client.post("/jobs/scout", headers=h, json={"queries": ["dashboard"]}).json() == []


def test_reject_and_edit_reasons_feed_analytics(client):
    h = auth(client)
    for jid in ("J-100", "J-106"):
        wait_run(client, h, client.post(f"/jobs/{jid}/analyze", headers=h).json()["run_id"])
    wait_run(client, h, client.post("/approvals/jobs/J-106", headers=h,
                                    json={"action": "reject", "reason": "not my niche"}).json()["run_id"])
    letter = client.get("/jobs/J-100", headers=h).json()["proposal_draft"]["cover_letter"]
    r = client.post("/approvals/jobs/J-100", headers=h, json={"action": "edit", "edited_text": letter.replace(
        "Below is the closest evidence from my portfolio and how I would approach it. ", "")}).json()
    assert wait_run(client, h, r["run_id"])["status"] == "submitted"
    a = client.get("/analytics", headers=h).json()
    assert a["rejection_reasons"] == ["not my niche"] and a["edit_rate"] == 0.5
    assert client.get("/memory", headers=h).json()["edits_logged"] == 1


def test_conversation_and_settings(client):
    h = auth(client)
    run = client.post("/threads/T-1/process?job_id=J-100", headers=h).json()
    assert wait_run(client, h, run["run_id"])["status"] == "awaiting_approval"
    t = client.get("/threads/T-1", headers=h).json()
    assert t["pending_approval"]["kind"] == "message"
    r = client.post("/approvals/threads/T-1", headers=h, json={"action": "approve"}).json()
    assert wait_run(client, h, r["run_id"])["status"] == "sent"
    assert client.put("/settings", headers=h, json={"maximum_risk_score": 0.0}).status_code == 200
    assert client.get("/settings", headers=h).json()["effective"]["thresholds"]["maximum_risk_score"] == 0.0
    run = client.post("/jobs/J-104/analyze", headers=h).json()
    assert wait_run(client, h, run["run_id"])["status"] == "skipped"   # new threshold applied


def test_degraded_banner_and_recovery(client):
    h = auth(client)
    backend = client.app.state.svc.backend
    backend.down = True
    run = client.post("/jobs/J-104/analyze", headers=h).json()
    assert wait_run(client, h, run["run_id"])["status"] == "waiting_for_marketplace"
    st = client.get("/status", headers=h).json()
    assert st["marketplace_ok"] is False and st["queued_while_down"] == 1
    backend.down = False
    assert client.post("/status/retry", headers=h).json()["resumed"][0]["status"] == "awaiting_approval"
    assert client.get("/status", headers=h).json()["marketplace_ok"]


def test_tenants_are_isolated(client):
    h1 = auth(client, "a1@example.com")
    wait_run(client, h1, client.post("/jobs/J-104/analyze", headers=h1).json()["run_id"])
    h2 = auth(client, "b2@example.com")
    assert client.get("/jobs", headers=h2).json() == []
    assert client.get("/approvals", headers=h2).json() == []
    assert client.get("/jobs/J-104", headers=h2).status_code == 404


def test_upload_validation(client):
    h = auth(client)
    bad = client.post("/portfolio/upload", headers=h, files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert bad.status_code == 415
    ok = client.post("/portfolio/upload", headers=h, files={"file": ("kafka.md", b"---\ntype: case_study\n---\nBuilt Kafka consumers for payments.", "text/markdown")})
    assert ok.status_code == 200 and ok.json()["chunks_indexed"] == 1
