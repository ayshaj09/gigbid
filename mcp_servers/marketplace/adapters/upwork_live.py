"""Live Upwork adapter (A4): the official Upwork MCP server behind the same MarketplacePort.

* Transport: Streamable HTTP via langchain-mcp-adapters' MultiServerMCPClient.
* Auth: OAuth 2.1 access token, stored encrypted per user (apps/api/security.py (TokenStore)) and
  passed as a bearer header. Tokens are never logged.
* Writes: proposals and messages are created as *drafts only*. `submit_proposal` refuses: the
  user confirms on Upwork, as the platform requires.
* Reads: allowed on a schedule no more frequent than `marketplace.upwork_live.poll_interval_minutes`.
* No browser automation, no cookies, no scraping.

Tool names are mapped through `marketplace.upwork_live.tool_map` in config.yaml, so if Upwork
renames a tool the fix is a config edit. Response shapes are normalised in `_normalise_job`.
"""
from __future__ import annotations

import json
from typing import Any

from agent.marketplace_port import MarketplaceError, MarketplaceUnavailable


class UpworkLiveMarketplace:
    name = "upwork_live"

    def __init__(self, cfg: dict, user_id: str, token_provider=None, client_factory=None, **_):
        self.cfg = cfg
        self.live = cfg["marketplace"]["upwork_live"]
        self.tool_map: dict[str, str | None] = self.live["tool_map"]
        self.user_id = user_id
        self._token_provider = token_provider  # async callable(user_id) -> access token
        self._client_factory = client_factory  # injectable for tests
        self._tools: dict[str, Any] | None = None

    async def _load_tools(self) -> dict[str, Any]:
        if self._tools is not None:
            return self._tools
        if self._token_provider is None:
            raise MarketplaceUnavailable("Upwork account not connected (no OAuth token)")
        token = await self._token_provider(self.user_id)
        conn = {"upwork": {"transport": "streamable_http", "url": self.live["url"],
                           "headers": {"Authorization": f"Bearer {token}"}}}
        if self._client_factory:
            client = self._client_factory(conn)
        else:
            from langchain_mcp_adapters.client import MultiServerMCPClient

            client = MultiServerMCPClient(conn)
        try:
            tools = await client.get_tools()
        except Exception as exc:  # noqa: BLE001
            raise MarketplaceUnavailable(f"Upwork MCP unreachable: {exc}") from exc
        self._tools = {t.name: t for t in tools}
        return self._tools

    async def _call(self, op: str, **args) -> Any:
        name = self.tool_map.get(op)
        if not name:
            raise MarketplaceError(f"'{op}' is not permitted in live mode")
        tools = await self._load_tools()
        if name not in tools:
            raise MarketplaceError(f"Upwork MCP has no tool '{name}' (update tool_map)")
        try:
            out = await tools[name].ainvoke(args)
        except Exception as exc:  # noqa: BLE001
            raise MarketplaceUnavailable(f"Upwork tool {name} failed: {exc}") from exc
        if isinstance(out, str):
            try:
                return json.loads(out)
            except ValueError:
                return {"text": out}
        return out

    @staticmethod
    def _normalise_job(raw: dict) -> dict:
        budget = raw.get("budget") or {}
        return {
            "job_id": str(raw.get("id") or raw.get("job_id")),
            "client_id": str(raw.get("client_id") or (raw.get("client") or {}).get("id", "")),
            "title": raw.get("title", ""),
            "description": raw.get("description", ""),
            "category": raw.get("category", "other"),
            "required_skills": raw.get("skills") or raw.get("required_skills") or [],
            "budget": {"min": budget.get("min") or budget.get("amount"), "max": budget.get("max") or budget.get("amount"),
                       "type": "hourly" if raw.get("hourly") else "fixed"},
            "screening_questions": raw.get("questions") or [],
            "connects_cost": raw.get("connects_cost") or raw.get("connects") or 0,
            "posted_at": raw.get("posted_at") or raw.get("created_at"),
        }

    async def search_jobs(self, query, limit=20):
        out = await self._call("search_jobs", query=query, limit=limit)
        jobs = out.get("jobs", out) if isinstance(out, dict) else out
        return [self._normalise_job(j) for j in jobs]

    async def get_job(self, job_id):
        return self._normalise_job(await self._call("get_job", job_id=job_id))

    async def get_client_history(self, client_id):
        return await self._call("get_client_history", client_id=client_id)

    async def get_connects_balance(self):
        return await self._call("get_connects_balance")

    async def get_market_stats(self, category):
        return {"category": category, "fixed": None, "hourly": None, "note": "not available live"}

    async def create_proposal_draft(self, payload, idempotency_key, dry_run=False):
        if dry_run:
            return {"dry_run": True, "would_send": payload, "target": "upwork draft"}
        return await self._call("create_proposal_draft", **payload)

    async def submit_proposal(self, proposal_id, idempotency_key, dry_run=False):
        return {"proposal_id": proposal_id, "status": "draft_on_upwork",
                "note": "Confirm and submit this draft on Upwork. GigBid never submits in live mode."}

    async def get_proposal(self, proposal_id):
        return await self._call("get_proposal", proposal_id=proposal_id)

    async def list_messages(self, thread_id):
        out = await self._call("list_messages", thread_id=thread_id)
        return out.get("messages", out) if isinstance(out, dict) else out

    async def send_message(self, thread_id, text, idempotency_key, dry_run=False):
        if dry_run:
            return {"dry_run": True, "would_send": {"thread_id": thread_id, "text": text}}
        return await self._call("send_message", thread_id=thread_id, text=text)
