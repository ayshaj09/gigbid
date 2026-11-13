"""In-process harness: the three MCP servers on in-memory transports, a ToolBelt over them, and a
Runner. Used by tests, `make demo` and the eval runners, so they exercise the real MCP call path
(schemas, validation, idempotency, audit) without spawning processes."""
from __future__ import annotations

import contextlib
import json
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from mcp.shared.memory import create_connected_server_and_client_session

from agent.config import ROOT, load_config
from agent.config import _deep_merge as _merge
from agent.mcp_client import ToolBelt
from agent.runner import Runner
from mcp_servers.marketplace.adapters.gigsim import FixtureGigSim
from mcp_servers.marketplace.server import build_server as build_marketplace
from mcp_servers.portfolio.server import build_server as build_portfolio
from mcp_servers.workspace.server import build_server as build_workspace


@contextlib.asynccontextmanager
async def harness(tmp_dir: str | Path, cfg_overrides: dict | None = None, backend=None, checkpointer=None,
                  store=None, persona: str = "ai_engineer", servers=("portfolio", "marketplace", "workspace")):
    base = {"models": {"profile": "offline"}, "marketplace": {"max_requests_per_minute": 6000}}
    cfg = load_config(_merge(base, cfg_overrides or {}))
    backend = backend or FixtureGigSim()
    built = {
        "portfolio": build_portfolio(cfg=cfg, persona=persona),
        "marketplace": build_marketplace(backend=backend, cfg=cfg, data_dir=Path(tmp_dir)),
        "workspace": build_workspace(data_dir=Path(tmp_dir)),
    }
    async with contextlib.AsyncExitStack() as stack:
        sessions = {}
        for name in servers:
            sessions[name] = await stack.enter_async_context(
                create_connected_server_and_client_session(built[name]._mcp_server))
        belt = await ToolBelt.from_sessions(sessions, cfg)
        belt.retries = 1
        belt.backoff = 0.01
        persona_doc = json.loads((ROOT / "data" / "fixtures" / f"persona_{persona}.json").read_text())
        runner = Runner(cfg, belt, persona_doc, checkpointer or InMemorySaver(), store or InMemoryStore(),
                        user_id="alice")
        runner.servers = built
        runner.backend = backend
        yield runner


def fixture_jobs() -> dict[str, dict]:
    return {j["job_id"]: j for j in json.loads((ROOT / "data" / "fixtures" / "jobs.json").read_text())}
