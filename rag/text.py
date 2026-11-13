"""Small text utilities shared by retrieval, verification and the rule-based nodes."""
from __future__ import annotations

import re

STOP = set("""a an and are as at be been but by can could did do does for from had has have how i if in
into is it its me my of on or our over should so such than that the their them then there these they
this to too up us was we were what when where which who will with would you your yours about after all
also any because before being both each few more most need needs other out own same some very via want
wants looking someone help please must able just like make build using use used work working job project
nice""".split())

_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#.\-]*[a-z0-9+#]|[a-z0-9]")


def tokens(text: str, keep_stop: bool = False) -> list[str]:
    out = _TOKEN.findall((text or "").lower())
    return out if keep_stop else [t for t in out if t not in STOP]


def content_set(text: str) -> set[str]:
    return set(tokens(text))


def stem(t: str) -> str:
    for suf in ("ing", "ies", "es", "ed", "s"):
        if len(t) > len(suf) + 3 and t.endswith(suf):
            return t[: -len(suf)]
    return t


def stem_set(text: str) -> set[str]:
    return {stem(t) for t in tokens(text)}


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])|\n{1,}", (text or "").strip())
    return [p.strip() for p in parts if p and p.strip()]


def overlap(query: str, doc: str) -> float:
    """Fraction of the query's content stems present in the doc (0..1)."""
    q, d = stem_set(query), stem_set(doc)
    return len(q & d) / len(q) if q else 0.0
