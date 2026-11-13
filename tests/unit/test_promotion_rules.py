from langgraph.store.memory import InMemoryStore

from agent.memory.promotion_rules import extract_edit_patterns, promote_outcomes, promote_style
from agent.memory.store import delete_style_rule, record_edit, style_rules

BEFORE = "Hello there, I am passionate about data. I built a churn model. I tuned thresholds. Call?"
AFTER = "I built a churn model. I tuned thresholds. Call?"


def test_edit_patterns():
    pats = extract_edit_patterns(BEFORE, AFTER)
    assert "cut_first_sentence" in pats


def test_one_off_edit_is_not_promoted(cfg):
    log = [{"before": BEFORE, "after": AFTER, "patterns": extract_edit_patterns(BEFORE, AFTER)}]
    assert promote_style(log, cfg) == []


def test_consistent_edits_promoted_and_contradiction_blocks(cfg):
    e = {"before": BEFORE, "after": AFTER, "patterns": extract_edit_patterns(BEFORE, AFTER)}
    assert "cut_first_sentence" in promote_style([e, e, e], cfg)
    b2 = "I built it fast."
    a2 = "I am passionate. I built it fast."  # adds 'passionate' back
    pats = ["removed_phrase:passionate"]
    log = [{"before": "I am passionate. x", "after": "x", "patterns": pats}] * 3 + [{"before": b2, "after": a2, "patterns": []}]
    assert "removed_phrase:passionate" not in promote_style(log, cfg)


async def test_store_promotion_and_user_delete(cfg):
    store = InMemoryStore()
    for _ in range(3):
        await record_edit(store, "u1", BEFORE, AFTER, cfg)
    assert "cut_first_sentence" in await style_rules(store, "u1")
    assert await style_rules(store, "someone_else") == []          # tenant-scoped
    await delete_style_rule(store, "u1", "cut_first_sentence")
    await record_edit(store, "u1", BEFORE, AFTER, cfg)            # deleted rules are not re-promoted
    assert "cut_first_sentence" not in await style_rules(store, "u1")


def test_outcome_needs_min_samples(cfg):
    rows = [{"category": "ai_ml", "outcome": "replied", "opening": "Your RAG misses SKUs."}] * 4
    assert promote_outcomes(rows, cfg) == {}
    stats = promote_outcomes(rows + [{"category": "ai_ml", "outcome": "ignored"}], cfg)
    assert stats["ai_ml"]["n"] == 5 and stats["ai_ml"]["reply_rate"] == 0.8
