"""Shared plumbing for GigBid's own MCP servers: audit log, rate limiter, idempotency, auth."""
from __future__ import annotations

import asyncio
import hmac
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from agent.guardrails import mask_obj

DATA_DIR = Path(os.environ.get("GIGBID_DATA_DIR", Path(__file__).resolve().parent.parent / "data" / "processed"))


class AuditLog:
    """Append-only JSONL audit log: user, tool, arguments, result, trace id. PII is masked and
    secret-looking keys are redacted before writing. The file is opened in append mode only;
    there is no update or delete API."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write(self, *, user_id: str, tool: str, args: dict, result: Any, trace_id: str | None, ok: bool = True):
        entry = {
            "ts": time.time(),
            "user_id": user_id,
            "tool": tool,
            "args": mask_obj(args),
            "result": mask_obj(result),
            "trace_id": trace_id,
            "ok": ok,
        }
        line = json.dumps(entry, default=str)
        with self._lock, open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]


class RateLimiter:
    """Per-user token bucket. Waits politely up to `max_wait_s`, then refuses. Configured below
    GigSim's own limit so GigBid never trips the simulator's 429s in normal operation."""

    def __init__(self, per_minute: int, max_wait_s: float = 5.0):
        self.rate = per_minute / 60.0
        self.capacity = max(1, per_minute // 4)  # small burst
        self.max_wait_s = max_wait_s
        self._buckets: dict[str, tuple[float, float]] = {}

    async def acquire(self, user_id: str) -> None:
        deadline = time.monotonic() + self.max_wait_s
        while True:
            tokens, last = self._buckets.get(user_id, (float(self.capacity), time.monotonic()))
            now = time.monotonic()
            tokens = min(self.capacity, tokens + (now - last) * self.rate)
            if tokens >= 1:
                self._buckets[user_id] = (tokens - 1, now)
                return
            self._buckets[user_id] = (tokens, now)
            wait = (1 - tokens) / self.rate
            if now + wait > deadline:
                raise RuntimeError(f"RATE_LIMITED: retry in {wait:.1f}s")
            await asyncio.sleep(wait)


class IdempotencyStore:
    """Persists (user, tool, key) -> result so a retried write returns the first result instead of
    acting twice. SQLite so it survives server restarts."""

    def __init__(self, path: Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS idem (user_id TEXT, tool TEXT, key TEXT, result TEXT, ts REAL,"
            " PRIMARY KEY (user_id, tool, key))"
        )
        self.conn.commit()
        self._lock = threading.Lock()

    def get(self, user_id: str, tool: str, key: str) -> dict | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT result FROM idem WHERE user_id=? AND tool=? AND key=?", (user_id, tool, key)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, user_id: str, tool: str, key: str, result: dict) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT OR IGNORE INTO idem VALUES (?,?,?,?,?)",
                (user_id, tool, key, json.dumps(result, default=str), time.time()),
            )
            self.conn.commit()


def parse_tokens(spec: str | None) -> dict[str, str]:
    """MCP_TOKENS="token1:alice,token2:bob" -> {token: user_id}."""
    out = {}
    for pair in (spec or "").split(","):
        if ":" in pair:
            tok, user = pair.split(":", 1)
            out[tok.strip()] = user.strip()
    return out


class BearerAuthMiddleware:
    """ASGI middleware for the Streamable HTTP endpoint: requires `Authorization: Bearer <token>`
    and pins the request to that token's user (exposed as scope['gigbid_user'])."""

    def __init__(self, app, tokens: dict[str, str]):
        self.app = app
        self.tokens = tokens

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"").decode()
        token = auth[7:] if auth.lower().startswith("bearer ") else ""
        user = next((u for t, u in self.tokens.items() if hmac.compare_digest(t, token)), None)
        if not user:
            body = b'{"error":"unauthorized"}'
            await send({"type": "http.response.start", "status": 401,
                        "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": body})
            return
        scope["gigbid_user"] = user
        return await self.app(scope, receive, send)


def run_server(mcp, default_port: int):
    """stdio by default (local agents); `MCP_TRANSPORT=http` serves Streamable HTTP with bearer auth."""
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        mcp.run("stdio")
        return
    import uvicorn

    tokens = parse_tokens(os.environ.get("MCP_TOKENS"))
    if not tokens:
        raise SystemExit("MCP_TOKENS must be set for HTTP transport (e.g. 'longrandomtoken:alice')")
    app = BearerAuthMiddleware(mcp.streamable_http_app(), tokens)
    uvicorn.run(app, host=os.environ.get("MCP_HOST", "0.0.0.0"), port=int(os.environ.get("MCP_PORT", default_port)))
