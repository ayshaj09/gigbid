"""Graph state (C2).

Three things are kept apart:
  * State (this module): what one job or one conversation needs right now.
  * Execution trace: `trace` entries here are *pointers* (node, tool, args hash, trace id); the full
    tool arguments/results go to the append-only audit log and the tracing backend, never into
    long-term memory.
  * Long-term memory: only promoted knowledge, written to a LangGraph store by
    agent/memory/promotion_rules.py.

Reducers are declared on every key that parallel branches (Analyst, Risk, Fit) may write.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def merge_evidence(left: list[dict] | None, right: list[dict] | None) -> list[dict]:
    """Union of evidence by evidence_id, keeping the highest score."""
    by_id: dict[str, dict] = {e["evidence_id"]: e for e in (left or [])}
    for item in right or []:
        cur = by_id.get(item["evidence_id"])
        if cur is None or item.get("score", 0) > cur.get("score", 0):
            by_id[item["evidence_id"]] = item
    return sorted(by_id.values(), key=lambda e: -e.get("score", 0))


SEVERITY = ["dead_letter", "needs_attention", "blocked"]


def merge_status(left: str | None, right: str | None) -> str | None:
    """Parallel branches may both set a status in one step; the most severe wins."""
    for s in SEVERITY:
        if s in (left, right):
            return s
    return right if right is not None else left


def last_non_empty(left, right):
    return right if right else left


def merge_usage(left: dict | None, right: dict | None) -> dict:
    out = dict(left or {})
    for key, value in (right or {}).items():
        out[key] = out.get(key, 0) + value
    return out


class BidState(TypedDict, total=False):
    # identity
    user_id: str
    persona_id: str
    job_id: str
    # inputs
    job: dict[str, Any]
    # parallel analyses (each branch writes its own key; shared keys have reducers)
    job_spec: dict[str, Any]
    risk_report: dict[str, Any]
    fit_report: dict[str, Any]
    evidence: Annotated[list[dict[str, Any]], merge_evidence]
    # decision and pricing
    decision: dict[str, Any]
    price_quote: dict[str, Any]
    # drafting loop
    proposal_draft: dict[str, Any]
    verification: dict[str, Any]
    critique: dict[str, Any]
    critiques: Annotated[list[dict[str, Any]], operator.add]
    revisions: int
    compliance_verdict: dict[str, Any]
    # human in the loop and side effects
    dry_run_preview: dict[str, Any]
    approval: dict[str, Any]
    submission: dict[str, Any]
    outcome: dict[str, Any]
    # control
    status: Annotated[str, merge_status]  # running | awaiting_approval | submitted | skipped | watching | rejected | blocked | needs_attention | dead_letter
    status_reason: Annotated[str, last_non_empty]
    steps: Annotated[int, operator.add]
    usage: Annotated[dict[str, float], merge_usage]  # tokens_in, tokens_out, usd, per-node keys
    trace: Annotated[list[dict[str, Any]], operator.add]
    errors: Annotated[list[str], operator.add]


class ConversationState(TypedDict, total=False):
    user_id: str
    persona_id: str
    thread_id: str
    job_id: str
    messages: list[dict[str, Any]]
    last_client_message: dict[str, Any]
    intent: dict[str, Any]
    proposed_slots: list[str]
    reply_draft: dict[str, Any]
    compliance_verdict: dict[str, Any]
    dry_run_preview: dict[str, Any]
    approval: dict[str, Any]
    sent: dict[str, Any]
    status: str
    status_reason: str
    steps: Annotated[int, operator.add]
    usage: Annotated[dict[str, float], merge_usage]
    trace: Annotated[list[dict[str, Any]], operator.add]
    errors: Annotated[list[str], operator.add]


# Backwards-compatible name used by the starter kit.
GigBidState = BidState
