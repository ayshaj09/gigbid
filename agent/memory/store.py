"""Long-term memory on a LangGraph BaseStore (InMemoryStore in tests, PostgresStore in prod).

Namespaces per user (tenant-scoped by construction):
  ("users", u, "edit_log")     raw edit events: input to promotion, not memory
  ("users", u, "style")        PROMOTED style rules            <- promotion_rules.promote_style
  ("users", u, "outcome_log")  raw outcome events: input to promotion, not memory
  ("users", u, "outcome")      PROMOTED per-category stats     <- promotion_rules.promote_outcomes
Users can list and delete promoted items (Settings -> Memory viewer).
"""
from __future__ import annotations

import time
import uuid

from agent.memory.promotion_rules import extract_edit_patterns, promote_outcomes, promote_style


def _ns(user: str, kind: str) -> tuple[str, ...]:
    return ("users", user, kind)


async def _log(store, user: str, kind: str) -> list[dict]:
    items = await store.asearch(_ns(user, kind), limit=1000)
    return [i.value for i in sorted(items, key=lambda i: i.value.get("ts", 0))]


async def record_edit(store, user: str, before: str, after: str, cfg: dict) -> list[str]:
    patterns = extract_edit_patterns(before, after)
    await store.aput(_ns(user, "edit_log"), uuid.uuid4().hex,
              {"before": before, "after": after, "patterns": patterns, "ts": time.time()})
    promoted = promote_style(await _log(store, user, "edit_log"), cfg)
    deleted = {i.key for i in await store.asearch(_ns(user, "style_deleted"), limit=1000)}
    for rule in promoted:
        if rule not in deleted:
            await store.aput(_ns(user, "style"), rule, {"rule": rule, "promoted_at": time.time(),
                                                 "by": "promote_style(min_occurrences, window, no contradiction)"})
    return promoted


async def style_rules(store, user: str) -> list[str]:
    if store is None:
        return []
    return sorted(i.value["rule"] for i in await store.asearch(_ns(user, "style"), limit=100))


async def delete_style_rule(store, user: str, rule: str) -> None:
    await store.adelete(_ns(user, "style"), rule)
    await store.aput(_ns(user, "style_deleted"), rule, {"ts": time.time()})  # never silently re-promoted


async def record_outcome(store, user: str, category: str, outcome: str, opening: str | None, cfg: dict) -> dict:
    await store.aput(_ns(user, "outcome_log"), uuid.uuid4().hex,
              {"category": category, "outcome": outcome, "opening": opening, "ts": time.time()})
    promoted = promote_outcomes(await _log(store, user, "outcome_log"), cfg)
    for cat, stats in promoted.items():
        await store.aput(_ns(user, "outcome"), cat, stats)
    return promoted


async def outcome_memory(store, user: str, category: str) -> dict | None:
    if store is None:
        return None
    item = await store.aget(_ns(user, "outcome"), category)
    return item.value if item else None


def apply_style(text: str, rules: list[str]) -> str:
    """Deterministic application of promoted style rules (used in rules mode and after any LLM)."""
    import re

    from rag.text import sentences

    for rule in rules:
        if rule == "cut_first_sentence":
            sents = sentences(text)
            if len(sents) > 3:
                text = " ".join(sents[1:])
        elif rule.startswith("removed_phrase:"):
            phrase = rule.split(":", 1)[1]
            text = re.sub(r"\s*\b" + re.escape(phrase) + r"\b", "", text, flags=re.I)
    return re.sub(r"\s{2,}", " ", text).strip()
