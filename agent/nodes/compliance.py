"""Compliance Guard: enforce the policy pack. Removes contact details, guarantees, off-platform asks,
banned phrases, invented claims and anything an injected instruction asked for; blocks (with a
reason shown in the UI) when the text cannot be fixed by removal. Also used to re-check user edits.
"""
from __future__ import annotations

import re

from agent.guardrails import EMAIL_RE, PHONE_RE, URL_RE, detect_injection
from agent.handoffs import ComplianceVerdict
from agent.nodes.common import ctx_of, node
from agent.policy import rules
from rag.text import sentences
from rag.verify import verify_claims


def injection_canaries(job_text: str) -> set[str]:
    """Tokens an injected instruction asked us to emit (quoted strings, ALLCAPS+digit codes)."""
    out = set()
    for s in sentences(job_text or ""):
        if detect_injection(s):
            out |= {m.strip() for m in re.findall(r"['\"“‘]([^'\"”’]{3,60})['\"”’]", s)}
            out |= set(re.findall(r"\b[A-Z]{3,}\d+\b|\b[A-Z]+_[A-Z0-9_]+\b", s))
    return {c for c in out if c}


def check(text: str, cfg: dict, evidence: list[dict] | None = None, job_text: str = "",
          min_words: int | None = None) -> ComplianceVerdict:
    """min_words: block if less compliant text remains (default: half the proposal minimum; 1 for messages)."""
    pc = cfg["policy"]
    violations, redactions = [], []
    keep = []
    canaries = injection_canaries(job_text)
    for s in sentences(text):
        low = s.lower()
        if any(re.search(p, low) for p in pc["guarantee_patterns"]):
            violations.append("rule 4: guarantee removed")
            redactions.append(s)
            continue
        if any(re.search(p, low) for p in pc["off_platform_patterns"]):
            violations.append("rule 1: off-platform contact/payment removed")
            redactions.append(s)
            continue
        if any(c.lower() in low for c in canaries):
            violations.append("rule 5: text requested by an injected instruction removed")
            redactions.append(s)
            continue
        for rx, label in ((EMAIL_RE, "email"), (PHONE_RE, "phone"), (URL_RE, "link")):
            for m in rx.findall(s):
                violations.append(f"rule 1: {label} removed")
                redactions.append(m)
                s = s.replace(m, "").replace("  ", " ")
        keep.append(s)
    cleaned = " ".join(keep)
    for phrase in pc["banned_phrases"]:
        if re.search(r"\b" + re.escape(phrase) + r"\b", cleaned, re.I):
            violations.append(f"banned phrase removed: '{phrase}'")
            redactions.append(phrase)
            cleaned = re.sub(r"\s*\b" + re.escape(phrase) + r"\b", "", cleaned, flags=re.I)
    if evidence is not None:
        rep, cleaned2 = verify_claims(cleaned, evidence, None, cfg)
        if rep.unsupported_before:
            violations.append(f"rule 3: {rep.unsupported_before} claim(s) without portfolio evidence removed")
            redactions += rep.removed
            cleaned = cleaned2
    blocked_reasons = []
    for r in rules(cfg, "compliance"):
        if r["type"] == "forbid_regex" and re.search(r["pattern"], cleaned, re.I):
            if r.get("action", "remove") == "block":
                blocked_reasons.append(f"policy {r.get('id', '')}: {r.get('reason', r['pattern'])}")
            else:
                cleaned = re.sub(r["pattern"], "", cleaned, flags=re.I)
                violations.append(f"policy {r.get('id', '')}: {r.get('reason', 'removed')}")
        elif r["type"] == "require_phrase" and r["text"].lower() not in cleaned.lower():
            cleaned = cleaned.rstrip() + " " + r["text"]
            violations.append(f"policy {r.get('id', '')}: added required text ({r.get('reason', '')})")
        elif r["type"] == "max_words" and len(cleaned.split()) > r["words"]:
            blocked_reasons.append(f"policy {r.get('id', '')}: over {r['words']} words")
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    floor = pc["min_proposal_words"] // 2 if min_words is None else min_words
    if len(cleaned.split()) < floor:
        blocked_reasons.append("too little compliant text left after removals")
    return ComplianceVerdict(allowed=not blocked_reasons, violations=violations + blocked_reasons,
                             redactions=redactions, cleaned_text=cleaned)


@node("compliance")
async def compliance(state, runtime):
    ctx = ctx_of(runtime)
    draft = dict(state["proposal_draft"])
    job = state["job"]
    verdict = check(draft["cover_letter"], ctx.cfg, state.get("evidence", []), job.get("description", ""))
    answers = [check(a, ctx.cfg, None, job.get("description", "")).cleaned_text for a in draft.get("screening_answers", [])]
    draft.update(cover_letter=verdict.cleaned_text, screening_answers=answers)
    out = {"compliance_verdict": verdict.model_dump(), "proposal_draft": draft}
    if not verdict.allowed:
        out.update(status="blocked", status_reason="; ".join(verdict.violations))
    return out
