from mcp.shared.memory import create_connected_server_and_client_session as connect

from agent.config import load_config
from mcp_servers.portfolio.server import build_server


async def test_tools_resources_prompts():
    srv = build_server(cfg=load_config(), persona="ai_engineer")
    async with connect(srv._mcp_server) as c:
        names = {t.name for t in (await c.list_tools()).tools}
        assert {"search_evidence", "get_case_study", "list_skills", "match_requirements"} <= names
        assert all(t.annotations.readOnlyHint for t in (await c.list_tools()).tools)
        templates = {t.uriTemplate for t in (await c.list_resource_templates()).resourceTemplates}
        assert {"portfolio://case/{evidence_id}", "portfolio://proposal/{evidence_id}"} <= templates
        prompts = {p.name for p in (await c.list_prompts()).prompts}
        assert "answer_screening_question" in prompts

        r = await c.call_tool("search_evidence", {"requirement": "Celery task queue with retries", "k": 3})
        item = r.structuredContent["items"][0]
        assert item["evidence_id"] == "cs-celery-etl"
        assert {"type", "source", "date", "outcome"} <= set(item)

        r = await c.call_tool("search_evidence", {"requirement": "proposal", "types": ["past_proposal"], "outcome": "won"})
        assert {i["evidence_id"] for i in r.structuredContent["items"]} == {"prop-won-rag"}

        res = await c.read_resource("portfolio://case/cs-churn")
        assert "churn" in res.contents[0].text.lower()
        p = await c.get_prompt("answer_screening_question", {"question": "How do you handle imbalance?"})
        assert "search_evidence" in p.messages[0].content.text


async def test_unknown_case_is_tool_error():
    srv = build_server(cfg=load_config(), persona="ai_engineer")
    async with connect(srv._mcp_server) as c:
        r = await c.call_tool("get_case_study", {"evidence_id": "nope"})
        assert r.isError
