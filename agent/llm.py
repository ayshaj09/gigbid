"""Per-node model routing (Models section): every node's model is set in config, never in code.

Providers:
  * openai_compatible - Ollama, vLLM, llama.cpp server, Groq, OpenRouter, Together, OpenAI...
  * rules             - no LLM; nodes use their deterministic implementation (tests, CI, offline).

Structured output is parsed from JSON in the reply rather than relying on provider-specific
tool-calling, so the same code works across open-model hosts.
"""
from __future__ import annotations

import json
import os
import re
import time
from string import Template
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from agent.config import load_prompt

T = TypeVar("T", bound=BaseModel)


class LLMUnavailable(RuntimeError):
    """Raised when no model is configured for a node; callers fall back to rules."""


def _extract_json(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)  # qwen3 reasoning blocks
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fenced:
        return fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in model output")
    return text[start : end + 1]


def render_prompt(name: str, **variables: Any) -> str:
    body = load_prompt(name)
    return Template(body).safe_substitute({k: v if isinstance(v, str) else json.dumps(v, default=str)
                                           for k, v in variables.items()})


class LLMRouter:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.models_cfg = cfg["models"]
        self.profile_name = self.models_cfg["profile"]
        self.profile = self.models_cfg["profiles"][self.profile_name]
        self._clients: dict[str, Any] = {}

    # -- routing ---------------------------------------------------------------------------
    def model_for(self, node: str) -> str | None:
        if self.profile["provider"] == "rules":
            return None
        return self.profile.get("nodes", {}).get(node)

    def enabled(self, node: str) -> bool:
        model = self.model_for(node)
        return bool(model) and model != "configure-me"

    def _client(self, model: str):
        if model not in self._clients:
            from langchain_openai import ChatOpenAI

            base_url = os.environ.get(self.profile["base_url_env"], "http://localhost:11434/v1")
            api_key = os.environ.get(self.profile["api_key_env"], "ollama")
            self._clients[model] = ChatOpenAI(
                model=model,
                base_url=base_url,
                api_key=api_key,
                temperature=self.models_cfg.get("temperature", 0.2),
                timeout=self.profile.get("node_timeout_s", self.models_cfg.get("node_timeout_s", 60)),
                max_retries=0,  # retries are handled here so fallback can kick in
            )
        return self._clients[model]

    def _cost(self, tokens_in: int, tokens_out: int) -> float:
        price = self.profile.get("usd_per_mtok", {"input": 0, "output": 0})
        return (tokens_in * price["input"] + tokens_out * price["output"]) / 1_000_000

    # -- calls -----------------------------------------------------------------------------
    async def complete(self, node: str, system: str, user: str) -> tuple[str, dict]:
        """Return (text, usage). Tries the node model, then the fallback model for cheap nodes."""
        if not self.enabled(node):
            raise LLMUnavailable(node)
        candidates = [self.model_for(node)]
        fb = self.profile.get("fallback")
        if fb and node in self.profile.get("cheap_nodes", []) and fb not in candidates:
            candidates.append(fb)
        retries = self.models_cfg.get("node_max_retries", 2)
        last_exc: Exception | None = None
        for model in candidates:
            for attempt in range(retries + 1):
                t0 = time.perf_counter()
                try:
                    msg = await self._client(model).ainvoke(
                        [("system", system + self.profile.get("system_suffix", "")), ("user", user)]
                    )
                    meta = getattr(msg, "usage_metadata", None) or {}
                    tin, tout = meta.get("input_tokens", 0), meta.get("output_tokens", 0)
                    usage = {
                        "tokens_in": tin,
                        "tokens_out": tout,
                        "usd": self._cost(tin, tout),
                        f"llm_s.{node}": time.perf_counter() - t0,
                        f"tokens.{node}": tin + tout,
                    }
                    return str(msg.content), usage
                except Exception as exc:  # noqa: BLE001 - provider errors vary widely
                    last_exc = exc
                    await _sleep_backoff(attempt)
        raise LLMUnavailable(f"{node}: all models failed: {last_exc}")

    async def structured(self, node: str, prompt: str, schema: type[T], **variables: Any) -> tuple[T, dict]:
        """Render agent/prompts/<prompt>.md, call the node's model, validate into `schema`."""
        system = render_prompt(prompt, **variables)
        user = (
            "Respond with ONE JSON object matching this JSON schema and nothing else:\n"
            + json.dumps(schema.model_json_schema())
        )
        text, usage = await self.complete(node, system, user)
        try:
            return schema.model_validate_json(_extract_json(text)), usage
        except (ValueError, ValidationError) as exc:
            # one repair attempt
            text2, usage2 = await self.complete(
                node, system, user + f"\nYour previous output was invalid ({exc}). Return valid JSON only."
            )
            usage = {k: usage.get(k, 0) + usage2.get(k, 0) for k in set(usage) | set(usage2)}
            return schema.model_validate_json(_extract_json(text2)), usage


async def _sleep_backoff(attempt: int) -> None:
    import asyncio

    await asyncio.sleep(min(0.25 * (2**attempt), 4))
