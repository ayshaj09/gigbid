"""Runtime context and the node wrapper shared by every agent node.

The wrapper gives every node the same discipline (C4, C7, R8):
  * step and token budgets: exceeding either moves the thread to `needs_attention`
  * a trace pointer per node (name, latency, trace id) in state; full args go to the audit log
  * unexpected exceptions -> `dead_letter` with the error, so one bad job never kills the worker
  * MarketplaceUnavailable is re-raised on purpose: the run stops at a checkpoint, the runner
    marks it `waiting_for_marketplace`, and resuming later continues from the failed node
"""
from __future__ import annotations

import functools
import time
import traceback
from dataclasses import dataclass, field
from typing import Any

from langgraph.errors import GraphBubbleUp

from agent.llm import LLMRouter
from agent.marketplace_port import MarketplacePort, MarketplaceUnavailable, McpMarketplace, get_marketplace

TERMINAL = {"skipped", "watching", "blocked", "rejected", "submitted", "needs_attention", "dead_letter", "sent"}


@dataclass
class GigBidContext:
    cfg: dict
    belt: Any                     # agent.mcp_client.ToolBelt
    llm: LLMRouter
    persona: dict
    user_id: str = "default"
    trace_id: str | None = None
    marketplace_override: MarketplacePort | None = None  # e.g. UpworkLiveMarketplace
    extras: dict = field(default_factory=dict)

    def marketplace(self, agent: str) -> MarketplacePort:
        if self.marketplace_override is not None:
            return self.marketplace_override
        if self.cfg["marketplace"]["mode"] == "gigsim":
            return McpMarketplace(self.belt.for_agent(agent), user_id=self.user_id, trace_id=self.trace_id)
        return get_marketplace(self.cfg, user_id=self.user_id)

    def tools(self, agent: str):
        return self.belt.for_agent(agent)


def ctx_of(runtime) -> GigBidContext:
    return runtime.context


def budgets_exceeded(state: dict, cfg: dict, kind: str = "job") -> str | None:
    b = cfg["budgets"]
    if state.get("steps", 0) >= b["max_graph_steps"]:
        return f"step budget exceeded ({state.get('steps')} >= {b['max_graph_steps']})"
    usage = state.get("usage") or {}
    tokens = usage.get("tokens_in", 0) + usage.get("tokens_out", 0)
    limit = b["max_tokens_per_job"] if kind == "job" else b["max_tokens_per_conversation"]
    if tokens >= limit:
        return f"token budget exceeded ({int(tokens)} >= {limit})"
    return None


def node(name: str, kind: str = "job"):
    """Decorator for async node functions `fn(state, runtime) -> dict`."""

    def deco(fn):
        @functools.wraps(fn)
        async def wrapper(state, runtime):
            ctx = ctx_of(runtime)
            if state.get("status") in TERMINAL:
                return {}
            reason = budgets_exceeded(state, ctx.cfg, kind)
            if reason:
                return {"status": "needs_attention", "status_reason": reason, "steps": 1,
                        "trace": [{"node": name, "event": "budget", "reason": reason}]}
            t0 = time.perf_counter()
            try:
                out = await fn(state, runtime) or {}
            except (MarketplaceUnavailable, GraphBubbleUp):
                raise  # degraded mode / interrupt(): must reach LangGraph untouched
            except Exception as exc:  # noqa: BLE001
                return {"status": "dead_letter", "status_reason": f"{name}: {exc}", "steps": 1,
                        "errors": [f"{name}: {exc!r}\n{traceback.format_exc(limit=3)}"],
                        "trace": [{"node": name, "event": "error", "error": repr(exc)}]}
            dt = time.perf_counter() - t0
            out = dict(out)
            out["steps"] = 1
            out.setdefault("trace", [])
            out["trace"] = out["trace"] + [{"node": name, "latency_s": round(dt, 4), "trace_id": ctx.trace_id}]
            usage = dict(out.get("usage") or {})
            usage[f"latency_s.{name}"] = usage.get(f"latency_s.{name}", 0) + dt
            out["usage"] = usage
            return out

        wrapper.node_name = name
        return wrapper

    return deco
