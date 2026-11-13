"""Claim verification node (B3): runs between the Writer and the Critic. Unsupported claims are
removed before the Critic sees the draft; before/after counts are kept for reporting (R5)."""
from __future__ import annotations

from agent.nodes.common import ctx_of, node
from rag.verify import verify_claims


@node("verify")
async def verifier(state, runtime):
    ctx = ctx_of(runtime)
    draft = dict(state["proposal_draft"])
    evidence = state.get("evidence", [])
    cited = {c["text"]: c["evidence_ids"] for c in draft.get("claims", [])}
    report, cleaned = verify_claims(draft["cover_letter"], evidence, cited, ctx.cfg)
    answers, removed_answers = [], 0
    for ans in draft.get("screening_answers", []):
        r, c = verify_claims(ans, evidence, cited, ctx.cfg)
        removed_answers += r.unsupported_before
        answers.append(c or "I would rather discuss this on a call than guess.")
    draft.update(cover_letter=cleaned, screening_answers=answers)
    rep = report.model_dump()
    rep["unsupported_in_answers"] = removed_answers
    return {"proposal_draft": draft, "verification": rep}
