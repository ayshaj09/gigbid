"""MCP client setup (A6): one ToolBelt per run, per-agent tool allowlists, timeouts, bounded retries
with backoff, and a clear degraded signal when a server is down.

Production: `ToolBelt.connect(cfg)` opens sessions through langchain-mcp-adapters'
MultiServerMCPClient (stdio or Streamable HTTP per config). Tests: `ToolBelt.from_sessions(...)`
with in-memory MCP client sessions, so the exact same call path is exercised.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import time
from typing import Any

from mcp import ClientSession

from agent.guardrails import mask_obj
from agent.marketplace_port import MarketplaceError, MarketplaceUnavailable


class ToolNotAllowed(PermissionError):
    pass


class ToolBelt:
    def __init__(self, sessions: dict[str, ClientSession], cfg: dict, stack: contextlib.AsyncExitStack | None = None):
        self.sessions = sessions
        self.cfg = cfg
        self._stack = stack
        self.tool_server: dict[str, str] = {}
        self.timeout = cfg.get("mcp", {}).get("tool_timeout_s", 15)
        self.retries = cfg["marketplace"].get("max_retries", 3)
        self.backoff = cfg["marketplace"].get("backoff_base_s", 0.5)
        self.calls: list[dict] = []  # execution trace (pointers + masked args), not memory
        self.down: set[str] = set()

    # ---- construction --------------------------------------------------------------------
    @classmethod
    async def from_sessions(cls, sessions: dict[str, ClientSession], cfg: dict) -> ToolBelt:
        belt = cls(sessions, cfg)
        await belt._index_tools()
        return belt

    @classmethod
    async def connect(cls, cfg: dict, servers: list[str] | None = None) -> ToolBelt:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        conns = {}
        for name, spec in cfg["mcp"]["servers"].items():
            if servers and name not in servers:
                continue
            if spec["transport"] == "stdio":
                conns[name] = {"transport": "stdio", "command": spec["command"], "args": spec["args"]}
            else:
                conns[name] = {"transport": "streamable_http", "url": spec["url"], "headers": spec.get("headers", {})}
        client = MultiServerMCPClient(conns)
        stack = contextlib.AsyncExitStack()
        sessions = {}
        for name in conns:
            try:
                sessions[name] = await stack.enter_async_context(client.session(name))
            except Exception:  # noqa: BLE001 - a dead server must not take the others down
                pass
        belt = cls(sessions, cfg, stack)
        belt.down = set(conns) - set(sessions)
        await belt._index_tools()
        return belt

    async def close(self):
        if self._stack:
            await self._stack.aclose()

    async def _index_tools(self):
        for server, session in self.sessions.items():
            for tool in (await session.list_tools()).tools:
                self.tool_server[tool.name] = server

    # ---- calls ---------------------------------------------------------------------------
    async def call(self, tool: str, args: dict[str, Any]) -> Any:
        server = self.tool_server.get(tool)
        if server is None:
            if tool in {"search_jobs", "get_job", "get_client_history", "get_connects_balance", "get_market_stats",
                        "create_proposal_draft", "submit_proposal", "list_messages", "send_message"}:
                raise MarketplaceUnavailable(f"marketplace MCP server is down (no tool {tool})")
            raise MarketplaceError(f"unknown tool {tool}")
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            t0 = time.perf_counter()
            try:
                res = await asyncio.wait_for(self.sessions[server].call_tool(tool, args), self.timeout)
            except (asyncio.TimeoutError, OSError, ConnectionError) as exc:
                last = MarketplaceUnavailable(f"{server} MCP server not responding: {exc!r}")
            except Exception as exc:  # noqa: BLE001 - closed streams etc.
                if "Closed" in type(exc).__name__ or "closed" in str(exc).lower():
                    last = MarketplaceUnavailable(f"{server} MCP server connection closed")
                else:
                    raise
            else:
                self.calls.append({"tool": tool, "server": server, "args": mask_obj(args), "ok": not res.isError,
                                   "latency_s": round(time.perf_counter() - t0, 4)})
                if res.isError:
                    text = res.content[0].text if res.content else "error"
                    if "UNAVAILABLE" in text or "RATE_LIMITED" in text:
                        last = MarketplaceUnavailable(text)
                    else:
                        raise MarketplaceError(text)
                else:
                    if res.structuredContent is not None:
                        sc = res.structuredContent
                        return sc["result"] if set(sc) == {"result"} else sc
                    text = res.content[0].text if res.content else "null"
                    try:
                        return json.loads(text)
                    except ValueError:
                        return text
            if attempt < self.retries:
                await asyncio.sleep(self.backoff * 2**attempt)
        self.down.add(server)
        raise last or MarketplaceUnavailable(server)

    def for_agent(self, agent: str):
        """A6: a call_tool restricted to the agent's allowlist from config."""
        allowed = set(self.cfg["mcp"]["allowlists"].get(agent, []))

        async def call(tool: str, args: dict[str, Any]) -> Any:
            if tool not in allowed:
                raise ToolNotAllowed(f"agent '{agent}' may not call '{tool}'")
            return await self.call(tool, args)

        return call
