"""Critic: grounding, personalisation, coverage, length; sends the draft back with concrete
instructions at most `budgets.max_revisions` times (enforced by the graph router)."""
from __future__ import annotations

import re

from agent.handoffs import Critique
from agent.llm import LLMUnavailable
from agent.nodes.common import ctx_of, node
from rag.text import overlap, sentences

GENERIC_OPENINGS = re.compile(r"^(?:hi|hello|dear|i am|i'm|my name|greetings|i have read)\b", re.I)
GENERIC_PHRASES = ["i am passionate", "i have read your job", "dear sir", "i am the best", "i am confident i can",
                   "many years of experience", "perfect fit for this job"]


def rule_critique(draft: dict, spec: dict, fit: dict, verification: dict, cfg: dict,
                  evidence: list[dict] | None = None) -> Critique:
    issues, instructions = [], []
    text = draft["cover_letter"]
    words = len(text.split())
    pc = cfg["policy"]
    if words > pc["max_proposal_words"]:
        issues.append(f"length: {words} words > {pc['max_proposal_words']}")
        instructions.append(f"shorten to under {pc['max_proposal_words']} words")
    if words < pc["min_proposal_words"]:
        issues.append(f"length: {words} words < {pc['min_proposal_words']}")
        instructions.append("add coverage: address the main requirements with evidence")
    sents = sentences(text)
    if sents and GENERIC_OPENINGS.match(sents[0]):
        issues.append("generic opening")
        instructions.append("personalise the opening around the client's specific problem")
    low = text.lower()
    for p in GENERIC_PHRASES:
        if p in low:
            issues.append(f"generic phrase: '{p}'")
            instructions.append(f"remove '{p}'")
    if verification.get("unsupported_before", 0):
        issues.append(f"grounding: {verification['unsupported_before']} unsupported claim(s) were removed")
        instructions.append("only restate facts present in the cited evidence")
    strong = [m for m in fit.get("matrix", []) if m["strength"] == "strong"]
    uncovered = [m for m in strong if max((overlap(m["requirement"], s) for s in sents), default=0) < 0.2
                 and not any(eid in text for eid in m["evidence_ids"])]
    cited_ids = set(draft.get("evidence_ids", []))
    cited = [e for e in (evidence or []) if e["evidence_id"] in cited_ids]

    def covered_by_cited(m) -> bool:
        if set(m["evidence_ids"]) & cited_ids:
            return True
        return any(overlap(m["requirement"], f"{e['text']} {' '.join(e.get('skills', []))}") >= 0.5 for e in cited)

    uncovered = [m for m in uncovered if not covered_by_cited(m)]
    if uncovered:
        issues.append(f"coverage: {len(uncovered)} evidenced requirement(s) not addressed")
        instructions.append("coverage: mention " + "; ".join(m["requirement"][:60] for m in uncovered[:2]))
    if len(draft.get("screening_answers", [])) < len(spec.get("screening_questions", [])):
        issues.append("screening questions unanswered")
        instructions.append("answer every screening question")
    return Critique(passed=not issues, issues=issues, instructions=instructions)


@node("critic")
async def critic(state, runtime):
    ctx = ctx_of(runtime)
    draft, verification = state["proposal_draft"], state.get("verification", {})
    crit = rule_critique(draft, state["job_spec"], state["fit_report"], verification, ctx.cfg,
                         state.get("evidence", []))
    usage, errors = {}, []
    if ctx.llm.enabled("critic"):
        pc = ctx.cfg["policy"]
        try:
            llm_crit, usage = await ctx.llm.structured(
                "critic", "critic", Critique, min_words=str(pc["min_proposal_words"]),
                max_words=str(pc["max_proposal_words"]), job_spec=state["job_spec"],
                verification=verification, draft=draft["cover_letter"])
            crit = Critique(passed=crit.passed and llm_crit.passed, issues=crit.issues + llm_crit.issues,
                            instructions=crit.instructions + llm_crit.instructions)
        except (LLMUnavailable, ValueError) as exc:
            errors.append(f"critic llm fallback: {exc}")
    revisions = state.get("revisions", 0) + (0 if crit.passed else 1)
    return {"critique": crit.model_dump(), "critiques": [{**crit.model_dump(), "revision": state.get("revisions", 0)}],
            "revisions": revisions, "usage": usage, "errors": errors}
