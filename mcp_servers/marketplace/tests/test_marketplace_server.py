"""Marketplace MCP server through an in-memory MCP client (A7)."""
import contextlib
import json

import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect

from agent.config import load_config
from mcp_servers.marketplace.adapters.gigsim import FixtureGigSim
from mcp_servers.marketplace.server import build_server

LETTER = "Your nightly ETL fails silently; I replaced cron with Celery and Redis for a logistics client."


@contextlib.asynccontextmanager
async def client(tmp_path, backend=None, **cfg_over):
    cfg = load_config(cfg_over or None)
    srv = build_server(backend=backend or FixtureGigSim(), cfg=cfg, data_dir=tmp_path)
    async with connect(srv._mcp_server) as c:
        yield c, srv


async def test_annotations_and_schemas(tmp_path):
    async with client(tmp_path) as (c, _):
        tools = {t.name: t for t in (await c.list_tools()).tools}
        assert tools["get_job"].annotations.readOnlyHint is True
        assert tools["submit_proposal"].annotations.destructiveHint is True
        assert tools["submit_proposal"].annotations.idempotentHint is True
        assert "idempotency_key" in tools["create_proposal_draft"].inputSchema["required"]
        assert tools["create_proposal_draft"].outputSchema is not None
        assert tools["search_jobs"].inputSchema["properties"]["limit"]["maximum"] == 50


async def test_input_constraints_enforced(tmp_path):
    async with client(tmp_path) as (c, _):
        r = await c.call_tool("get_job", {"job_id": "../../etc/passwd"})
        assert r.isError
        r = await c.call_tool("create_proposal_draft", {"job_id": "J-100", "cover_letter": "short", "bid_amount": 10,
                                                        "idempotency_key": "k" * 10})
        assert r.isError


async def test_dry_run_previews_without_side_effects(tmp_path):
    backend = FixtureGigSim()
    async with client(tmp_path, backend) as (c, _):
        r = await c.call_tool("create_proposal_draft", {"job_id": "J-104", "cover_letter": LETTER, "bid_amount": 50,
                                                        "idempotency_key": "preview-123", "dry_run": True})
        sc = r.structuredContent
        assert sc["dry_run"] and sc["would_send"]["cover_letter"] == LETTER and sc["cost_connects"] == 10
        assert backend.proposals == {}


async def test_idempotent_submit_spends_connects_once(tmp_path):
    backend = FixtureGigSim()
    async with client(tmp_path, backend) as (c, _):
        args = {"job_id": "J-104", "cover_letter": LETTER, "bid_amount": 50, "idempotency_key": "idem-0001"}
        d1 = (await c.call_tool("create_proposal_draft", args)).structuredContent
        d2 = (await c.call_tool("create_proposal_draft", args)).structuredContent
        assert d2["idempotent_replay"] and d1["result"]["proposal_id"] == d2["result"]["proposal_id"]
        pid = d1["result"]["proposal_id"]
        for _ in range(3):
            await c.call_tool("submit_proposal", {"proposal_id": pid, "idempotency_key": "idem-0001-s"})
        assert len(backend.submissions) == 1 and backend.connects["default"] == 70


async def test_audit_log_masks_pii_and_has_trace_id(tmp_path):
    async with client(tmp_path) as (c, srv):
        await c.call_tool("send_message", {"thread_id": "T-1", "text": "write to me at boss@example.com",
                                           "idempotency_key": "msg-00001", "trace_id": "tr-1"})
        rows = srv.audit.read()
        assert rows[-1]["trace_id"] == "tr-1" and "example.com" not in json.dumps(rows)


async def test_unavailable_backend_is_reported(tmp_path):
    backend = FixtureGigSim()
    backend.down = True
    async with client(tmp_path, backend) as (c, _):
        r = await c.call_tool("get_job", {"job_id": "J-100"})
        assert r.isError and "UNAVAILABLE" in r.content[0].text


async def test_rate_limiter_refuses_bursts(tmp_path):
    async with client(tmp_path, marketplace={"max_requests_per_minute": 4}) as (c, srv):
        results = [await c.call_tool("get_connects_balance", {}) for _ in range(3)]
        assert any(r.isError and "RATE_LIMITED" in r.content[0].text for r in results)


@pytest.mark.parametrize("token,status", [("good", 200), ("bad", 401)])
async def test_http_bearer_auth(token, status):
    import httpx

    from mcp_servers.common import BearerAuthMiddleware

    async def ok_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": scope["gigbid_user"].encode()})

    app = BearerAuthMiddleware(ok_app, {"good": "alice"})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as h:
        r = await h.post("/mcp", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == status
