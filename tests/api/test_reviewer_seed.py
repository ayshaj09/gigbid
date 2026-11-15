"""The deployed app recreates its reviewer login from env vars on every boot (ephemeral disks)."""
from apps.api.db import DB
from apps.api.security import verify_password
from apps.api.service import Service


def test_reviewer_seeded_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB", str(tmp_path / "app.sqlite"))
    monkeypatch.setenv("REVIEWER_EMAIL", "Reviewer@Example.com")
    monkeypatch.setenv("REVIEWER_PASSWORD", "review-pass-123")
    svc = Service()
    uid = svc.seed_reviewer()
    assert uid and svc.seed_reviewer() == uid          # second boot: same account, no duplicate
    u = DB(str(tmp_path / "app.sqlite")).user_by_email("reviewer@example.com")
    assert u["onboarded"] and u["persona_id"] == "ai_engineer"
    assert verify_password("review-pass-123", u["password_hash"])


def test_no_reviewer_without_env(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB", str(tmp_path / "app.sqlite"))
    monkeypatch.delenv("REVIEWER_EMAIL", raising=False)
    assert Service().seed_reviewer() is None
