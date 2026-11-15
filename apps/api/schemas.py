"""Request/response models. The web client's TypeScript types are generated from these via OpenAPI."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TokenOut(BaseModel):
    token: str
    user_id: str
    onboarded: bool


class Me(BaseModel):
    user_id: str
    email: str
    persona_id: str | None
    onboarded: bool
    settings: dict[str, Any]


class Onboarding(BaseModel):
    persona_id: str = Field(min_length=1, max_length=40)
    hourly_rate_usd: float = Field(gt=0, le=1000)
    floor_usd: float = Field(ge=0, le=100000)
    weekly_connects_budget: int = Field(ge=0, le=1000)
    saved_searches: list[str] = Field(default_factory=list, max_length=10)
    marketplace_mode: Literal["gigsim", "upwork_live"] = "gigsim"


class SettingsIn(BaseModel):
    minimum_fit_score: float | None = Field(default=None, ge=0, le=1)
    watch_fit_score: float | None = Field(default=None, ge=0, le=1)
    maximum_risk_score: float | None = Field(default=None, ge=0, le=1)
    auto_skip_low_fit: bool | None = None
    weekly_connects_budget: int | None = Field(default=None, ge=0, le=1000)
    hourly_rate_usd: float | None = Field(default=None, gt=0, le=1000)
    floor_usd: float | None = Field(default=None, ge=0)
    saved_searches: list[str] | None = Field(default=None, max_length=10)
    model_profile: Literal["open", "paid", "offline"] | None = None


class JobRow(BaseModel):
    job_id: str
    title: str | None
    category: str | None
    status: str | None
    action: str | None
    fit: float | None
    risk: float | None
    is_scam: bool
    connects: int | None
    price: float | None
    reason: str | None
    updated: float | None


class RunOut(BaseModel):
    run_id: str
    kind: str
    target_id: str
    events_url: str


class Decision(BaseModel):
    action: Literal["approve", "edit", "reject"]
    edited_text: str | None = Field(default=None, max_length=8000)
    reason: str | None = Field(default=None, max_length=500)


class Outcome(BaseModel):
    outcome: Literal["replied", "interview", "won", "hired", "ignored", "lost"]


class ScoutIn(BaseModel):
    queries: list[str] | None = None
    analyse: bool = True
