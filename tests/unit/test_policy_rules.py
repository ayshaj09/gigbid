"""The change-request hook: new platform rules are config, not code."""
from agent.config import load_config
from agent.nodes.compliance import check
from agent.nodes.decision import decide
from agent.nodes.pricing import price

SPEC = {"budget_min": 800, "budget_max": 1500, "budget_type": "fixed", "category": "ai_ml", "connects_cost": 12}
RISK = {"score": 0.1, "flags": [], "is_scam": False, "client_quality": 0.9}
FIT = {"score": 0.9, "reasons": [], "matrix": []}
PERSONA = {"floor_usd": 300, "hourly_rate_usd": 40}


def test_scam_is_always_skipped(cfg):
    assert decide(SPEC, {**RISK, "is_scam": True, "flags": ["unpaid_work"]}, FIT, cfg).action == "skip"


def test_connects_surcharge_rule_from_config():
    cfg = load_config({"models": {"profile": "offline"}, "policy": {"extra_rules": [
        {"id": "CR-1", "stage": "pricing", "type": "connects_surcharge", "extra_connects": 4, "categories": ["ai_ml"]}]}})
    q = price(SPEC, FIT, RISK, PERSONA, {}, 80, cfg)
    assert q.connects_cost == 16 and any("CR-1" in r for r in q.rationale)


def test_min_budget_rule_from_config():
    cfg = load_config({"models": {"profile": "offline"}, "policy": {"extra_rules": [
        {"id": "CR-2", "stage": "decision", "type": "min_budget", "usd": 2000}]}})
    d = decide(SPEC, RISK, FIT, cfg)
    assert d.action == "skip" and "CR-2" in d.reasons[0]


def test_require_phrase_rule_from_config():
    cfg = load_config({"models": {"profile": "offline"}, "policy": {"extra_rules": [
        {"id": "CR-3", "stage": "compliance", "type": "require_phrase", "text": "Drafted with AI assistance.",
         "reason": "AI disclosure"}]}})
    text = " ".join(["Your pipeline fails silently and needs retries."] * 8)
    v = check(text, cfg)
    assert v.cleaned_text.endswith("Drafted with AI assistance.")


def test_price_respects_floor(cfg):
    q = price({**SPEC, "budget_min": 50, "budget_max": 100}, FIT, RISK, PERSONA, {}, 80, cfg)
    assert q.amount >= 300


def test_skip_when_far_below_floor():
    cfg = load_config()
    persona = {"floor_usd": 300, "hourly_rate_usd": 50}
    cheap = {**SPEC, "budget_type": "fixed", "budget_max": 100}
    assert decide(cheap, RISK, {**FIT, "score": 0.9}, cfg, persona).action == "skip"
    ok = {**SPEC, "budget_type": "fixed", "budget_max": 400}
    assert decide(ok, RISK, {**FIT, "score": 0.9}, cfg, persona).action == "bid"
    low_rate = {**SPEC, "budget_type": "hourly", "budget_max": 20}
    assert decide(low_rate, RISK, {**FIT, "score": 0.9}, cfg, persona).action == "skip"
