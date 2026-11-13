"""Policy pack + configurable extra rules (the change-request hook).

A platform policy update should be absorbed by adding an entry to `policy.extra_rules` in
config.yaml, not by editing nodes. Supported rule types and the stage that applies them:

  stage: decision
    - {type: min_budget, usd: 50}                          skip jobs whose max budget is below usd
    - {type: skip_category, categories: [crypto]}          never bid in these categories
    - {type: max_connects_per_job, connects: 16}           watch instead of bid above this cost
  stage: pricing
    - {type: connects_surcharge, extra_connects: 2, categories: [ai_ml]}   extra cost per bid
    - {type: connects_multiplier, factor: 1.5}
  stage: compliance
    - {type: forbid_regex, pattern: '...', action: remove|block, reason: '...'}
    - {type: require_phrase, text: 'Drafted with AI assistance.', reason: 'AI disclosure rule'}
    - {type: max_words, words: 250}
"""
from __future__ import annotations

from pathlib import Path

from agent.config import ROOT


def policy_text(cfg: dict) -> str:
    path = ROOT / cfg["policy"]["pack_path"]
    return Path(path).read_text(encoding="utf-8") if path.exists() else ""


def rules(cfg: dict, stage: str) -> list[dict]:
    return [r for r in cfg["policy"].get("extra_rules", []) or [] if r.get("stage") == stage]


def applies(rule: dict, category: str | None) -> bool:
    cats = rule.get("categories")
    return not cats or category in cats
