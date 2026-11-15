"""Small relational layer for the API: users, settings, job index, threads, runs, outcomes.

SQLite by default (APP_DB path); the schema is plain SQL so moving it to Postgres is a driver swap.
LangGraph checkpoints and long-term memory live in the checkpointer/store, not here: this
database only indexes them for listing, filtering and analytics.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
  persona_id TEXT, settings TEXT NOT NULL DEFAULT '{}', onboarded INTEGER NOT NULL DEFAULT 0, created REAL);
CREATE TABLE IF NOT EXISTS jobs (
  user_id TEXT, job_id TEXT, title TEXT, category TEXT, status TEXT, action TEXT, fit REAL, risk REAL,
  is_scam INTEGER, connects INTEGER, price REAL, reason TEXT, job TEXT, updated REAL,
  PRIMARY KEY (user_id, job_id));
CREATE TABLE IF NOT EXISTS threads (
  user_id TEXT, thread_id TEXT, job_id TEXT, status TEXT, intent TEXT, last_message TEXT, updated REAL,
  PRIMARY KEY (user_id, thread_id));
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, user_id TEXT, kind TEXT, target_id TEXT, status TEXT, events TEXT,
  started REAL, finished REAL, tokens REAL, usd REAL, error TEXT);
CREATE TABLE IF NOT EXISTS approvals (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, kind TEXT, target_id TEXT, action TEXT,
  reason TEXT, edited INTEGER, ts REAL);
CREATE TABLE IF NOT EXISTS outcomes (
  user_id TEXT, job_id TEXT, outcome TEXT, ts REAL, PRIMARY KEY (user_id, job_id));
"""


class DB:
    def __init__(self, path: str | None = None):
        path = path or os.environ.get("APP_DB", "data/processed/app.sqlite")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.lock = threading.Lock()

    def exec(self, sql: str, args: tuple = ()) -> None:
        with self.lock:
            self.conn.execute(sql, args)
            self.conn.commit()

    def one(self, sql: str, args: tuple = ()) -> dict | None:
        with self.lock:
            row = self.conn.execute(sql, args).fetchone()
        return dict(row) if row else None

    def all(self, sql: str, args: tuple = ()) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    # ---- users -----------------------------------------------------------------------------
    def user(self, user_id: str) -> dict | None:
        u = self.one("SELECT * FROM users WHERE id=?", (user_id,))
        if u:
            u["settings"] = json.loads(u["settings"])
        return u

    def user_by_email(self, email: str) -> dict | None:
        u = self.one("SELECT * FROM users WHERE email=?", (email.lower(),))
        if u:
            u["settings"] = json.loads(u["settings"])
        return u

    def save_settings(self, user_id: str, settings: dict, persona_id: str | None = None, onboarded: bool | None = None):
        u = self.user(user_id)
        self.exec("UPDATE users SET settings=?, persona_id=?, onboarded=? WHERE id=?",
                  (json.dumps(settings), persona_id or u["persona_id"],
                   int(u["onboarded"] if onboarded is None else onboarded), user_id))

    # ---- jobs index -----------------------------------------------------------------------
    def upsert_job(self, user_id: str, job: dict, state: dict[str, Any], status: str) -> None:
        fit = (state.get("fit_report") or {}).get("score")
        risk = state.get("risk_report") or {}
        self.exec(
            "INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id, job_id) DO UPDATE SET "
            "title=excluded.title, category=excluded.category, status=excluded.status, action=excluded.action, "
            "fit=excluded.fit, risk=excluded.risk, is_scam=excluded.is_scam, connects=excluded.connects, "
            "price=excluded.price, reason=excluded.reason, job=excluded.job, updated=excluded.updated",
            (user_id, job["job_id"], job.get("title"), (state.get("job_spec") or {}).get("category") or job.get("category"),
             status, (state.get("decision") or {}).get("action"), fit, risk.get("score"), int(bool(risk.get("is_scam"))),
             (state.get("price_quote") or {}).get("connects_cost", job.get("connects_cost")),
             (state.get("price_quote") or {}).get("amount"), state.get("status_reason"), json.dumps(job), time.time()))
