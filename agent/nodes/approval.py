"""Human approval (R4, C5) and the only node that spends Connects.

approval_prep  builds the payload: draft, evidence behind every claim, risk report, price rationale,
               Critic/Compliance notes and the marketplace dry_run preview (exact text + cost).
approval       `interrupt(payload)`; the graph thread is checkpointed and waits for the UI.
               Resume with Command(resume={"action": "approve"|"edit"|"reject", ...}).
               Edits are diffed into style memory and re-checked by Compliance; if Compliance had to
               change the edit, the user sees the cleaned text and approves again.
submit         create draft + submit with deterministic idempotency keys: after a crash, replaying
               this node returns the first result instead of submitting twice.
"""
from __future__ import annotations

from langgraph.types import interrupt

from agent.handoffs import ApprovalDecision
from agent.marketplace_port import idempotency_key
from agent.memory.store import record_edit
from agent.nodes.common import ctx_of, node
from agent.nodes.compliance import check


def _payload_args(state) -> dict:
    d, q = state["proposal_draft"], state["price_quote"]
    return {"job_id": state["job"]["job_id"], "cover_letter": d["cover_letter"], "bid_amount": q["amount"],
            "bid_type": q["basis"], "screening_answers": d.get("screening_answers", [])}


@node("approval_prep")
async def approval_prep(state, runtime):
    ctx = ctx_of(runtime)
    args = _payload_args(state)
    key = idempotency_key(ctx.user_id, args)
    preview = await ctx.marketplace("preview").create_proposal_draft(args, key, dry_run=True)
    return {"dry_run_preview": preview, "status": "awaiting_approval"}


@node("approval")
async def approval(state, runtime):
    ctx = ctx_of(runtime)
    draft = state["proposal_draft"]
    ev = {e["evidence_id"]: e for e in state.get("evidence", [])}
    checks = (state.get("verification") or {}).get("checks", [])
    payload = {
        "kind": "proposal",
        "job": {k: state["job"].get(k) for k in ("job_id", "title", "client_id")},
        "draft": draft,
        "claims": [{"claim": c["claim"], "label": c["label"],
                    "evidence": [{"id": i, "title": ev[i]["title"], "source": ev[i].get("source")} for i in c["evidence_ids"] if i in ev]}
                   for c in checks if c["label"] != "not_a_claim"],
        "risk_report": state.get("risk_report"),
        "price_quote": state.get("price_quote"),
        "critiques": state.get("critiques", []),
        "compliance": state.get("compliance_verdict"),
        "dry_run_preview": state.get("dry_run_preview"),
        "actions": ["approve", "edit", "reject"],
    }
    decision = ApprovalDecision.model_validate(interrupt(payload))

    if decision.action == "reject":
        return {"approval": decision.model_dump(), "status": "rejected",
                "status_reason": decision.reason or "rejected without a reason"}
    if decision.action == "approve":
        return {"approval": decision.model_dump(), "status": "approved"}

    # edit: diff into style memory, then re-check with Compliance
    before, after = draft["cover_letter"], decision.edited_text or ""
    if runtime.store is not None and after and after != before:
        await record_edit(runtime.store, ctx.user_id, before, after, ctx.cfg)
    verdict = check(after, ctx.cfg, state.get("evidence", []), state["job"].get("description", ""))
    new_draft = {**draft, "cover_letter": verdict.cleaned_text, "edited_by_user": True}
    if verdict.allowed and verdict.cleaned_text.strip() == " ".join(after.split()):
        return {"approval": decision.model_dump(), "proposal_draft": new_draft,
                "compliance_verdict": verdict.model_dump(), "status": "approved"}
    # Compliance changed or blocked the edit: show the user and ask again.
    return {"approval": {**decision.model_dump(), "needs_reapproval": True}, "proposal_draft": new_draft,
            "compliance_verdict": verdict.model_dump(), "status": "awaiting_approval"}


@node("submit")
async def submit(state, runtime):
    ctx = ctx_of(runtime)
    args = _payload_args(state)
    key = idempotency_key(ctx.user_id, args)
    mp = ctx.marketplace("submit")
    draft = await mp.create_proposal_draft(args, key, dry_run=False)
    proposal_id = (draft.get("result") or draft).get("proposal_id")
    res = await mp.submit_proposal(proposal_id, key + "-submit", dry_run=False)
    return {"submission": {"proposal_id": proposal_id, "idempotency_key": key, **res}, "status": "submitted"}
