"""B3 claim verification: split a draft into claims, check each against retrieved evidence, and
remove (or flag for rewrite) unsupported claims before the Critic sees the draft.

Labels: supported | partly_supported | unsupported | not_a_claim
  * not_a_claim: questions, greetings, calls to action, statements about the client's problem,
    and forward-looking plans ("I would start by...") which assert no past experience.
  * A claim's support is the best lexical-stem coverage against evidence it cites, falling back to
    all retrieved evidence. Any number in the claim (years, %, counts) must appear in the
    supporting evidence, or the claim is capped at partly_supported: invented metrics are the
    commonest fabrication.

An optional LLM judge (prompt: agent/prompts/claim_verifier.md) can replace the lexical score;
calibrate it against your own labels before trusting it (B4).
"""
from __future__ import annotations

import re

from agent.handoffs import ClaimCheck, VerificationReport
from rag.text import sentences, stem_set

FIRST_PERSON = re.compile(r"\b(?:I|I've|I'm|I'd|my|we|our|we've)\b")
PLAN = re.compile(r"\b(?:I|we)(?:'d| would| will|'ll| can| could| plan to| propose| suggest)\b", re.I)
PAST_MARKERS = re.compile(r"\b(?:before|previously|already|in the past|last year|have built|built|delivered|"
                          r"shipped|reached|cut|reduced|improved|fixed|replaced|trained|designed|deployed)\b", re.I)
NON_CLAIM_START = re.compile(r"^(?:hi|hello|dear|thanks|thank you|best|regards|cheers|looking forward|happy to|"
                             r"would you|could you|can we|shall we|let's|let me know|your|you|below|here)\b", re.I)
# Commercial terms are offers, not experience claims.
OFFER = re.compile(r"\b(?:proposed price|my (?:rate|price|quote|fee)|for the scope above|per hour|/hour)\b", re.I)
NUMBER = re.compile(r"\b\d+(?:[.,]\d+)?\s?%?|\b(?:one|two|three|four|five|six|seven|eight|nine|ten)\b", re.I)
WORD_NUM = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
            "eight": "8", "nine": "9", "ten": "10"}


def _numbers(text: str) -> set[str]:
    out = set()
    for m in NUMBER.findall(text or ""):
        m = m.strip().lower().replace(",", "").replace(" ", "")
        out.add(WORD_NUM.get(m, m).rstrip("%"))
    return out


def is_claim(sentence: str) -> bool:
    s = sentence.strip()
    if not s or s.endswith("?") or NON_CLAIM_START.match(s) or OFFER.search(s):
        return False
    if PLAN.search(s) and not PAST_MARKERS.search(s):
        return False
    return bool(FIRST_PERSON.search(s) or (_numbers(s) and PAST_MARKERS.search(s)))


def _support(claim: str, ev: dict) -> float:
    c = stem_set(claim) - {"i", "my", "we", "our", "ve", "client", "project"}
    d = stem_set(f"{ev.get('title', '')} {ev.get('text', '')} {' '.join(ev.get('skills', []))}")
    if not c:
        return 1.0
    score = len(c & d) / len(c)
    missing_numbers = _numbers(claim) - _numbers(ev.get("text", "") + " " + ev.get("title", ""))
    if missing_numbers:
        score = min(score, 0.45)  # a number not in the evidence can never be 'supported'
    return score


def verify_claims(draft: str, evidence: list[dict], cited: dict[str, list[str]] | None = None,
                  cfg: dict | None = None) -> tuple[VerificationReport, str]:
    """Return (report, cleaned_text). `cited` maps claim text -> evidence ids the writer cited."""
    vcfg = (cfg or {}).get("verification", {})
    hi, lo = vcfg.get("supported_threshold", 0.55), vcfg.get("partial_threshold", 0.30)
    by_id = {e["evidence_id"]: e for e in evidence}
    cited = cited or {}
    checks: list[ClaimCheck] = []
    kept, removed = [], []
    for sent in sentences(draft):
        if not is_claim(sent):
            checks.append(ClaimCheck(claim=sent, label="not_a_claim", score=1.0))
            kept.append(sent)
            continue
        cited_ids = next((ids for text, ids in cited.items() if text.strip() and text.strip() in sent), [])
        pool = [by_id[i] for i in cited_ids if i in by_id] or evidence
        scored = sorted(((_support(sent, e), e["evidence_id"]) for e in pool), reverse=True)
        best, best_id = scored[0] if scored else (0.0, None)
        label = "supported" if best >= hi else "partly_supported" if best >= lo else "unsupported"
        checks.append(ClaimCheck(claim=sent, label=label, score=round(best, 3),
                                 evidence_ids=[best_id] if best_id and label != "unsupported" else []))
        if label == "unsupported":
            removed.append(sent)
        else:
            kept.append(sent)
    n_unsupported = sum(c.label == "unsupported" for c in checks)
    action = vcfg.get("action_on_unsupported", "remove")
    cleaned = " ".join(kept) if action == "remove" else draft
    report = VerificationReport(checks=checks, unsupported_before=n_unsupported,
                                unsupported_after=0 if action == "remove" else n_unsupported, removed=removed)
    return report, cleaned
