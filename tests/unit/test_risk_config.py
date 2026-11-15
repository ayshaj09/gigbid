"""Risk rules come from config: hourly posts without a rate are not 'zero budget'; config-added
scam patterns (income bait, de-punctuated emails from the Kaggle fake postings) flag scams."""
from agent.config import load_config
from agent.nodes.risk_assessor import rule_risk

GOOD_CLIENT = {"payment_verified": True, "hires": 5, "jobs_posted": 6, "average_rating": 4.8, "total_spent_usd": 5000}
DESC = "We need a Python developer to build a REST API for our booking platform, long term contract with the team."


def test_hourly_without_rate_is_not_zero_budget():
    r = rule_risk({"title": "API", "description": DESC, "budget": {"type": "hourly", "max": None}}, GOOD_CLIENT, load_config())
    assert "zero_budget" not in r.flags and r.score < 0.6
    r = rule_risk({"title": "API", "description": DESC, "budget": {"type": "fixed", "max": None}}, GOOD_CLIENT, load_config())
    assert "zero_budget" in r.flags


def test_config_patterns_flag_income_bait():
    job = {"title": "clerk", "description": "earn 5000week immediate hiring contact now at julie64yahoocom flexible hours",
           "budget": {"type": "fixed", "max": 300}}
    r = rule_risk(job, GOOD_CLIENT, load_config())
    assert r.is_scam and {"income_bait", "off_platform_contact"} <= set(r.flags)


def test_new_rule_is_config_only():
    cfg = load_config()
    cfg["risk"]["patterns"]["crypto_task"] = r"\bmine bitcoin\b"
    cfg["risk"]["scam_flags"].append("crypto_task")
    r = rule_risk({"title": "x", "description": DESC + " Help us mine bitcoin.", "budget": {"type": "fixed", "max": 500}},
                  GOOD_CLIENT, cfg)
    assert r.is_scam
