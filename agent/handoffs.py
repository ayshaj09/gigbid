"""Structured hand-offs between agents (C3). Anything a later step decides on is one of these."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Requirement(BaseModel):
    id: str
    text: str
    skills: list[str] = Field(default_factory=list)
    must_have: bool = True


class JobSpec(BaseModel):
    job_id: str
    title: str
    category: str = "general"
    deliverables: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    budget_min: float | None = None
    budget_max: float | None = None
    budget_type: Literal["fixed", "hourly", "unknown"] = "unknown"
    timeline_days: int | None = None
    screening_questions: list[str] = Field(default_factory=list)
    hidden_needs: list[str] = Field(default_factory=list)
    connects_cost: int = 0
    client_id: str | None = None


class RiskReport(BaseModel):
    score: float = Field(ge=0, le=1)
    flags: list[str] = Field(default_factory=list)
    client_quality: float = Field(default=0.5, ge=0, le=1)
    injection_detected: bool = False
    is_scam: bool = False
    explanation: str


class EvidenceItem(BaseModel):
    evidence_id: str
    type: str
    title: str
    text: str
    source: str = ""
    date: str | None = None
    outcome: str | None = None
    skills: list[str] = Field(default_factory=list)
    score: float = 0.0


class RequirementMatch(BaseModel):
    requirement_id: str
    requirement: str
    evidence_ids: list[str] = Field(default_factory=list)
    strength: Literal["strong", "partial", "none"] = "none"


class FitReport(BaseModel):
    score: float = Field(ge=0, le=1)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    matrix: list[RequirementMatch] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class BidDecision(BaseModel):
    action: Literal["bid", "watch", "skip"]
    reasons: list[str] = Field(default_factory=list)
    auto: bool = False  # True when taken without a human (only ever for skip)


class PriceQuote(BaseModel):
    amount: float = Field(ge=0)
    currency: str = "USD"
    basis: Literal["fixed", "hourly"] = "fixed"
    fair_band: tuple[float, float] = (0.0, 0.0)
    connects_cost: int = 0
    connects_usd: float = 0.0
    connects_worth_it: bool = True
    rationale: list[str] = Field(default_factory=list)


class Claim(BaseModel):
    text: str
    evidence_ids: list[str] = Field(default_factory=list)


class ProposalDraft(BaseModel):
    job_id: str
    cover_letter: str
    claims: list[Claim] = Field(default_factory=list)
    screening_answers: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    revision: int = 0
    status: str = "pending_review"


class ClaimCheck(BaseModel):
    claim: str
    label: Literal["supported", "partly_supported", "unsupported", "not_a_claim"]
    score: float = 0.0
    evidence_ids: list[str] = Field(default_factory=list)


class VerificationReport(BaseModel):
    checks: list[ClaimCheck] = Field(default_factory=list)
    unsupported_before: int = 0
    unsupported_after: int = 0
    removed: list[str] = Field(default_factory=list)


class Critique(BaseModel):
    passed: bool
    issues: list[str] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)


class ComplianceVerdict(BaseModel):
    allowed: bool
    violations: list[str] = Field(default_factory=list)
    redactions: list[str] = Field(default_factory=list)
    cleaned_text: str = ""


class ApprovalDecision(BaseModel):
    action: Literal["approve", "edit", "reject"]
    edited_text: str | None = None
    reason: str | None = None
    approver: str = "user"


class MessageIntent(BaseModel):
    intent: Literal["question", "negotiation", "interview_request", "scam_signal", "other"]
    confidence: float = Field(default=0.5, ge=0, le=1)
    injection_detected: bool = False
    notes: str = ""


class ReplyDraft(BaseModel):
    thread_id: str
    text: str
    proposed_slots: list[str] = Field(default_factory=list)
    status: str = "pending_review"
