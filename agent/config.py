"""Configuration and prompt loading. Everything tunable lives in config.yaml or agent/prompts/."""
from __future__ import annotations

import copy
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get("GIGBID_CONFIG", ROOT / "agent" / "config.yaml"))
PROMPTS_DIR = ROOT / "agent" / "prompts"


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


@lru_cache(maxsize=4)
def _load(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_config(overrides: dict | None = None) -> dict[str, Any]:
    """Load config.yaml, then apply env overrides, then explicit overrides (tests)."""
    cfg = copy.deepcopy(_load(str(CONFIG_PATH)))
    if mode := os.environ.get("MARKETPLACE_MODE"):
        cfg["marketplace"]["mode"] = mode
    if profile := os.environ.get("MODEL_PROFILE"):
        cfg["models"]["profile"] = profile
    if variant := os.environ.get("RETRIEVAL_VARIANT"):
        cfg["retrieval"]["variant"] = variant
    if emb := os.environ.get("EMBEDDER_PROVIDER"):
        cfg["retrieval"]["embedder"]["provider"] = emb
    if emb_model := os.environ.get("EMBEDDER_MODEL"):
        cfg["retrieval"]["embedder"]["model"] = emb_model
    if rr := os.environ.get("RERANKER_PROVIDER"):
        cfg["retrieval"]["reranker"]["provider"] = rr
    if rpm := os.environ.get("MARKETPLACE_RPM"):
        cfg["marketplace"]["max_requests_per_minute"] = int(rpm)
    if overrides:
        cfg = _deep_merge(cfg, overrides)
    return cfg


def load_prompt(name: str) -> str:
    """Prompts are versioned markdown files; the first line is `<!-- version: N -->`."""
    path = PROMPTS_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8")


def prompt_version(name: str) -> str:
    first = load_prompt(name).splitlines()[0]
    return first.replace("<!--", "").replace("-->", "").replace("version:", "").strip()
