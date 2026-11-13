from mcp.shared.memory import create_connected_server_and_client_session as connect

from mcp_servers.workspace.server import build_server


async def test_slots_hold_and_conflict(tmp_path):
    srv = build_server(data_dir=tmp_path)
    async with connect(srv._mcp_server) as c:
        slots = (await c.call_tool("free_slots", {"days": 7})).structuredContent["slots"]
        assert 1 <= len(slots) <= 3
        start = slots[0]["start"]
        h = await c.call_tool("create_interview_hold", {"start": start, "title": "Interview: RAG chatbot"})
        assert h.structuredContent["status"] == "tentative"
        again = await c.call_tool("create_interview_hold", {"start": start, "title": "Clash"})
        assert again.isError
        slots2 = (await c.call_tool("free_slots", {"days": 7})).structuredContent["slots"]
        assert start not in [s["start"] for s in slots2]
        d = await c.call_tool("create_email_draft", {"to": "me@example.com", "subject": "Prep", "body": "Notes"})
        assert d.structuredContent["status"] == "draft"
