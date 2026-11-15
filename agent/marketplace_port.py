"""R1: the single marketplace port.

The graph only ever talks to a `MarketplacePort`. Which marketplace sits behind it is decided by
`marketplace.mode` in config.yaml:

  gigsim       -> McpMarketplace: calls our own Marketplace MCP server (mcp_servers/marketplace),
                  which wraps the GigSim REST API with schemas, idempotency, dry_run, audit log.
  upwork_live  -> UpworkLiveMarketplace (mcp_servers/marketplace/adapters/upwork_live.py): calls the
                  official Upwork MCP server over Streamable HTTP with the user's OAuth token.
                  Writes are drafts only; the user confirms on Upwork.

Switching mode changes which adapter `get_marketplace()` returns; no node code changes.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol, runtime_checkable


class MarketplaceError(RuntimeError):
    """A marketplace call failed in a way retrying will not fix (bad input, 4xx)."""


class MarketplaceUnavailable(MarketplaceError):
    """The marketplace or its MCP server cannot be reached. Callers enter degraded mode."""


class RateLimited(MarketplaceUnavailable):
    def __init__(self, retry_after_s: float = 5.0):
        super().__init__(f"rate limited; retry after {retry_after_s}s")
        self.retry_after_s = retry_after_s


@runtime_checkable
class MarketplacePort(Protocol):
    name: str

    async def search_jobs(self, query: str, limit: int = 20) -> list[dict[str, Any]]: ...
    async def get_job(self, job_id: str) -> dict[str, Any]: ...
    async def get_client_history(self, client_id: str) -> dict[str, Any]: ...
    async def get_connects_balance(self) -> dict[str, Any]: ...
    async def get_market_stats(self, category: str) -> dict[str, Any]: ...
    async def create_proposal_draft(
        self, payload: dict[str, Any], idempotency_key: str, dry_run: bool = False
    ) -> dict[str, Any]: ...
    async def submit_proposal(
        self, proposal_id: str, idempotency_key: str, dry_run: bool = False
    ) -> dict[str, Any]: ...
    async def get_proposal(self, proposal_id: str) -> dict[str, Any]: ...
    async def list_messages(self, thread_id: str) -> list[dict[str, Any]]: ...
    async def send_message(
        self, thread_id: str, text: str, idempotency_key: str, dry_run: bool = False
    ) -> dict[str, Any]: ...


def idempotency_key(*parts: Any) -> str:
    """Deterministic key: the same approved action always maps to the same key, so a retried or
    replayed call can never submit twice or spend Connects twice."""
    blob = json.dumps(parts, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:32]


class McpMarketplace:
    """Port adapter that calls the Marketplace MCP server's tools through an MCP session.

    `call_tool` is any async callable (tool_name, arguments) -> dict. In production it is backed
    by `agent.mcp_client.ToolBelt`; in tests by an in-memory MCP client session.
    """

    name = "gigsim"

    def __init__(self, call_tool, user_id: str = "default", trace_id: str | None = None):
        self._call = call_tool
        self.user_id = user_id
        self.trace_id = trace_id

    async def _tool(self, tool: str, **args) -> Any:
        args = {k: v for k, v in args.items() if v is not None}
        args.setdefault("user_id", self.user_id)
        if self.trace_id:
            args.setdefault("trace_id", self.trace_id)
        return await self._call(tool, args)

    async def search_jobs(self, query: str, limit: int = 20):
        return (await self._tool("search_jobs", query=query, limit=limit))["jobs"]

    async def get_job(self, job_id: str):
        return await self._tool("get_job", job_id=job_id)

    async def get_client_history(self, client_id: str):
        return await self._tool("get_client_history", client_id=client_id)

    async def get_connects_balance(self):
        return await self._tool("get_connects_balance")

    async def get_market_stats(self, category: str):
        return await self._tool("get_market_stats", category=category)

    async def create_proposal_draft(self, payload, idempotency_key, dry_run=False):
        return await self._tool(
            "create_proposal_draft", **payload, idempotency_key=idempotency_key, dry_run=dry_run
        )

    async def submit_proposal(self, proposal_id, idempotency_key, dry_run=False):
        return await self._tool(
            "submit_proposal", proposal_id=proposal_id, idempotency_key=idempotency_key, dry_run=dry_run
        )

    async def get_proposal(self, proposal_id: str):
        return await self._tool("get_proposal", proposal_id=proposal_id)

    async def list_messages(self, thread_id: str):
        return (await self._tool("list_messages", thread_id=thread_id))["messages"]

    async def send_message(self, thread_id, text, idempotency_key, dry_run=False):
        return await self._tool(
            "send_message", thread_id=thread_id, text=text, idempotency_key=idempotency_key, dry_run=dry_run
        )


def get_marketplace(cfg: dict, call_tool=None, user_id: str = "default", **kwargs) -> MarketplacePort:
    """Factory: the only place that knows which marketplace is live."""
    mode = cfg["marketplace"]["mode"]
    if mode == "gigsim":
        if call_tool is None:
            raise ValueError("gigsim mode needs an MCP call_tool (see agent.mcp_client.ToolBelt)")
        return McpMarketplace(call_tool, user_id=user_id, trace_id=kwargs.get("trace_id"))
    if mode == "upwork_live":
        from mcp_servers.marketplace.adapters.upwork_live import UpworkLiveMarketplace

        return UpworkLiveMarketplace(cfg, user_id=user_id, **kwargs)
    raise ValueError(f"unknown marketplace mode: {mode}")
