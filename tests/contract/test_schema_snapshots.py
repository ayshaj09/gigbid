"""A7: fails CI when a tool signature changes unintentionally.
Regenerate deliberately with:  UPDATE_SNAPSHOTS=1 pytest tests/contract"""
import json
import os
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect

from agent.config import load_config
from mcp_servers.marketplace.adapters.gigsim import FixtureGigSim
from mcp_servers.marketplace.server import build_server as mk
from mcp_servers.portfolio.server import build_server as pf
from mcp_servers.workspace.server import build_server as ws

SNAP = Path(__file__).parent / "snapshots"


def servers(tmp):
    cfg = load_config()
    return {"marketplace": mk(backend=FixtureGigSim(), cfg=cfg, data_dir=tmp), "portfolio": pf(cfg=cfg),
            "workspace": ws(data_dir=tmp)}


@pytest.mark.parametrize("name", ["marketplace", "portfolio", "workspace"])
async def test_tool_schemas_match_snapshot(name, tmp_path):
    srv = servers(tmp_path)[name]
    async with connect(srv._mcp_server) as c:
        tools = sorted((await c.list_tools()).tools, key=lambda t: t.name)
        current = [{"name": t.name, "input": t.inputSchema, "output": t.outputSchema,
                    "annotations": t.annotations.model_dump() if t.annotations else None} for t in tools]
    path = SNAP / f"{name}.json"
    if os.environ.get("UPDATE_SNAPSHOTS") or not path.exists():
        path.write_text(json.dumps(current, indent=1, sort_keys=True), encoding="utf-8")
        if not os.environ.get("UPDATE_SNAPSHOTS"):
            pytest.fail(f"snapshot {path.name} created; commit it")
    assert current == json.loads(path.read_text(encoding="utf-8")), f"{name} tool schema changed; rerun with UPDATE_SNAPSHOTS=1 if intended"
