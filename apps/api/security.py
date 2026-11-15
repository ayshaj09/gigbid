"""Auth (PBKDF2 password hashes + HS256 JWTs) and encrypted per-user OAuth token storage."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time

import jwt
from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

ALGO = "HS256"
TTL_S = 7 * 24 * 3600
_bearer = HTTPBearer(auto_error=False)


def secret_key() -> str:
    key = os.environ.get("APP_SECRET_KEY", "")
    if os.environ.get("APP_ENV") == "production" and (not key or key == "replace_me" or len(key) < 32):
        raise RuntimeError("APP_SECRET_KEY must be set to 32+ random characters in production")
    return key or "dev-only-insecure-key-change-me-please-0000"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return "pbkdf2$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_b64, dk_b64 = stored.split("$")
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), 310_000)
    return hmac.compare_digest(dk, base64.b64decode(dk_b64))


def issue_token(user_id: str) -> str:
    now = int(time.time())
    return jwt.encode({"sub": user_id, "iat": now, "exp": now + TTL_S}, secret_key(), algorithm=ALGO)


def current_user(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    token = creds.credentials if creds else request.query_params.get("token")  # EventSource can't set headers
    if not token:
        raise HTTPException(401, "not signed in")
    try:
        payload = jwt.decode(token, secret_key(), algorithms=[ALGO])
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "invalid or expired token") from exc
    user = request.app.state.svc.db.user(payload["sub"])
    if not user:
        raise HTTPException(401, "unknown user")
    return user


class TokenStore:
    """Upwork OAuth tokens encrypted at rest with Fernet (key: TOKEN_ENC_KEY). Never logged."""

    def __init__(self, db):
        key = os.environ.get("TOKEN_ENC_KEY") or base64.urlsafe_b64encode(hashlib.sha256(secret_key().encode()).digest()).decode()
        self.f = Fernet(key.encode())
        self.db = db
        db.exec("CREATE TABLE IF NOT EXISTS oauth_tokens (user_id TEXT PRIMARY KEY, blob BLOB, ts REAL)")

    def put(self, user_id: str, access_token: str) -> None:
        self.db.exec("INSERT OR REPLACE INTO oauth_tokens VALUES (?,?,?)",
                     (user_id, self.f.encrypt(access_token.encode()), time.time()))

    async def get(self, user_id: str) -> str:
        row = self.db.one("SELECT blob FROM oauth_tokens WHERE user_id=?", (user_id,))
        if not row:
            raise LookupError("no Upwork token for user")
        return self.f.decrypt(row["blob"]).decode()
