"""R7: explicit promotion rules. Nothing reaches long-term memory except through these functions.

Style memory (learned from the user's edits to drafts)
  An edit is diffed into candidate patterns:
    * removed_phrase:<phrase>   a 1-4 word phrase the user deleted
    * cut_first_sentence        the user deleted the opening sentence
    * shortened                 the user cut >= 25% of the words
  A pattern is PROMOTED only if it appears in >= `min_occurrences` distinct edits among the user's
  last `window` edits AND was never contradicted in that window (e.g. the phrase added back).
  One-off edits therefore never become rules.

Outcome memory (what won or got replies, per job category)
  A category's stats are PROMOTED only once it has >= `min_samples` recorded outcomes. Stored:
  counts, reply rate, win rate, and up to 3 opening sentences from proposals that won or got a
  reply (our own generated text, not raw tool output).
"""
from __future__ import annotations

import difflib
import re
from collections import Counter

from rag.text import sentences

GENERIC = {"the", "a", "an", "and", "to", "of", "in", "for", "on", "with", "i", "you", "your", "my", "is", "it"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def extract_edit_patterns(before: str, after: str) -> list[str]:
    patterns: set[str] = set()
    b_sents, a_sents = sentences(before), sentences(after)
    if b_sents and a_sents and _norm(b_sents[0]) not in {_norm(s) for s in a_sents}:
        patterns.add("cut_first_sentence")
    bw, aw = before.split(), after.split()
    if bw and len(aw) <= 0.75 * len(bw):
        patterns.add("shortened")
    sm = difflib.SequenceMatcher(a=[w.lower().strip(".,!") for w in bw], b=[w.lower().strip(".,!") for w in aw])
    for op, i1, i2, _, _ in sm.get_opcodes():
        if op in ("delete", "replace") and 1 <= i2 - i1 <= 4:
            phrase = " ".join(sm.a[i1:i2]).strip()
            if phrase and not set(phrase.split()) <= GENERIC:
                patterns.add(f"removed_phrase:{phrase}")
    return sorted(patterns)


def contradicts(pattern: str, before: str, after: str) -> bool:
    """A later edit that ADDS the phrase back contradicts a removed_phrase pattern."""
    if pattern.startswith("removed_phrase:"):
        phrase = pattern.split(":", 1)[1]
        return phrase not in _norm(before) and phrase in _norm(after)
    return False


def promote_style(edit_log: list[dict], cfg: dict) -> list[str]:
    """edit_log: chronological [{"before","after","patterns"}]. Returns promoted rules."""
    m = cfg["memory"]["style"]
    recent = edit_log[-m["window"]:]
    counts = Counter(p for e in recent for p in set(e["patterns"]))
    promoted = []
    for pattern, n in counts.items():
        if n < m["min_occurrences"]:
            continue
        n_contra = sum(contradicts(pattern, e["before"], e["after"]) for e in recent)
        if n_contra <= m["max_contradictions"]:
            promoted.append(pattern)
    return sorted(promoted)


def should_promote_style_edit(edit_count: int, consistent_pattern: bool) -> bool:
    """Kept for the starter kit's interface: the same rule in its simplest form."""
    return edit_count >= 3 and consistent_pattern


def promote_outcomes(outcome_log: list[dict], cfg: dict) -> dict[str, dict]:
    """outcome_log: [{"category","outcome": won|replied|ignored|lost, "opening"}]."""
    min_n = cfg["memory"]["outcome"]["min_samples"]
    by_cat: dict[str, list[dict]] = {}
    for o in outcome_log:
        by_cat.setdefault(o["category"], []).append(o)
    out = {}
    for cat, rows in by_cat.items():
        if len(rows) < min_n:
            continue
        replied = [r for r in rows if r["outcome"] in ("won", "replied", "interview", "hired")]
        out[cat] = {
            "n": len(rows),
            "reply_rate": round(len(replied) / len(rows), 3),
            "win_rate": round(sum(r["outcome"] in ("won", "hired") for r in rows) / len(rows), 3),
            "openings_that_worked": [r["opening"] for r in replied if r.get("opening")][:3],
        }
    return out
