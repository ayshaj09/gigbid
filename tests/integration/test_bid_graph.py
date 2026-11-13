"""Bid graph end to end on the fixture marketplace, through real (in-memory) MCP servers."""
import json

import pytest

from agent.config import ROOT
from agent.marketplace_port import MarketplaceUnavailable
from agent.testing import harness
from mcp_servers.marketplace.adapters.gigsim import FixtureGigSim

GOLD = json.loads((ROOT / "data/fixtures/gold.json").read_text())


async def test_decisions_match_hand_labels(tmp_path):
    async with harness(tmp_path) as r:
        for job_id, g in GOLD.items():
            res = await r.start_job(job_id)
            action = "bid" if res.status == "awaiting_approval" else res.state["decision"]["action"]
            assert action == g["action"], (job_id, res.state.get("status_reason"))
            assert bool(res.state["risk_report"]["is_scam"]) == g["scam"], job_id


async def test_parallel_branches_all_finish_before_decide(tmp_path):
    async with harness(tmp_path) as r:
        res = await r.start_job("J-104")
        nodes = [e["node"] for e in res.events]
        i_decide = nodes.index("decide")
        assert {"analyst", "risk_assessor", "fit_matcher"} <= set(nodes[:i_decide])
        assert nodes.count("decide") == 1


async def test_duplicate_repost_is_skipped(tmp_path):
    async with harness(tmp_path) as r:
        await r.start_job("J-100")
        res = await r.start_job("J-105")
        assert res.status == "skipped" and "duplicate of J-100" in res.state["status_reason"]


async def test_injected_instruction_is_ignored(tmp_path):
    async with harness(tmp_path) as r:
        res = await r.start_job("J-102")
        assert res.status == "awaiting_approval"
        assert "prompt_injection" in res.state["risk_report"]["flags"]
        assert "BANANA42" not in res.interrupt["draft"]["cover_letter"]


async def test_approval_payload_and_approve_submits_once(tmp_path):
    backend = FixtureGigSim()
    async with harness(tmp_path, backend=backend) as r:
        res = await r.start_job("J-104")
        p = res.interrupt
        assert p["dry_run_preview"]["dry_run"] and p["dry_run_preview"]["cost_connects"] == 10
        assert p["claims"] and all(c["evidence"] for c in p["claims"] if c["label"] == "supported")
        assert p["price_quote"]["rationale"] and p["risk_report"]
        assert backend.submissions == []                      # nothing sent before approval
        done = await r.resume_job("J-104", {"action": "approve"})
        assert done.status == "submitted"
        assert len(backend.submissions) == 1 and backend.connects["alice"] == 70


async def test_reject_with_reason(tmp_path):
    backend = FixtureGigSim()
    async with harness(tmp_path, backend=backend) as r:
        await r.start_job("J-106")
        res = await r.resume_job("J-106", {"action": "reject", "reason": "too far from my core work"})
        assert res.status == "rejected" and res.state["status_reason"] == "too far from my core work"
        assert backend.submissions == []


async def test_edit_is_rechecked_by_compliance_and_logged(tmp_path):
    backend = FixtureGigSim()
    async with harness(tmp_path, backend=backend) as r:
        res = await r.start_job("J-104")
        letter = res.interrupt["draft"]["cover_letter"]
        edited = letter + " Email me at me@example.com to go faster."
        res2 = await r.resume_job("J-104", {"action": "edit", "edited_text": edited})
        assert res2.status == "awaiting_approval"            # compliance changed the edit -> ask again
        assert "example.com" not in res2.interrupt["draft"]["cover_letter"]
        assert res2.interrupt["compliance"]["violations"]
        edits = await r.store.asearch(("users", "alice", "edit_log"))
        assert len(edits) == 1
        res3 = await r.resume_job("J-104", {"action": "approve"})
        assert res3.status == "submitted" and len(backend.submissions) == 1


async def test_critic_loop_is_bounded(tmp_path):
    over = {"policy": {"min_proposal_words": 400, "max_proposal_words": 900}}
    async with harness(tmp_path, cfg_overrides=over) as r:
        res = await r.start_job("J-104")
        writer_runs = [e for e in res.events if e["node"] == "writer"]
        assert len(writer_runs) == 3                           # first draft + max 2 rewrites
        assert len(res.state["critiques"]) == 3 and not res.state["critique"]["passed"]


async def test_step_budget_moves_thread_to_needs_attention(tmp_path):
    async with harness(tmp_path, cfg_overrides={"budgets": {"max_graph_steps": 5}}) as r:
        res = await r.start_job("J-104")
        assert res.status == "needs_attention" and "step budget" in res.state["status_reason"]


async def test_marketplace_outage_parks_then_recovers(tmp_path):
    backend = FixtureGigSim()
    async with harness(tmp_path, backend=backend) as r:
        backend.down = True
        res = await r.start_job("J-104")
        assert res.status == "waiting_for_marketplace"
        backend.down = False
        [res2] = await r.retry_waiting()
        assert res2.status == "awaiting_approval"


async def test_marketplace_server_killed(tmp_path):
    async with harness(tmp_path, servers=("portfolio", "workspace")) as r:
        res = await r.start_job("J-104")
        assert res.status == "waiting_for_marketplace" and "marketplace MCP server is down" in res.error


async def test_lost_response_after_submit_is_not_resubmitted(tmp_path):
    """The marketplace performs the submit but the response is lost; the node retries.
    Idempotency must make the second attempt a no-op."""
    class FlakyAfterSubmit(FixtureGigSim):
        failed = False

        async def submit_proposal(self, user_id, proposal_id, idem):
            res = await super().submit_proposal(user_id, proposal_id, idem)
            if not self.failed:
                self.failed = True
                raise MarketplaceUnavailable("connection reset after submit")
            return res

    backend = FlakyAfterSubmit()
    async with harness(tmp_path, backend=backend) as r:
        await r.start_job("J-104")
        res = await r.resume_job("J-104", {"action": "approve"})
        assert res.status == "submitted"
        assert len(backend.submissions) == 1 and backend.connects["alice"] == 70


async def test_crash_while_awaiting_approval_then_resume(tmp_path):
    """Kill everything while a proposal waits for approval; restart with the same durable
    checkpointer; approve; exactly one submission."""
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    db = str(tmp_path / "ckpt.sqlite")
    backend = FixtureGigSim()                     # the marketplace outlives our process
    async with AsyncSqliteSaver.from_conn_string(db) as saver:
        async with harness(tmp_path, backend=backend, checkpointer=saver) as r:
            res = await r.start_job("J-104")
            assert res.status == "awaiting_approval"
    # --- process gone; new process, new MCP sessions, same database ---
    async with AsyncSqliteSaver.from_conn_string(db) as saver2:
        async with harness(tmp_path, backend=backend, checkpointer=saver2) as r2:
            pending = await r2.job_state("J-104")
            assert pending.status == "awaiting_approval" and pending.interrupt["kind"] == "proposal"
            done = await r2.resume_job("J-104", {"action": "approve"})
            assert done.status == "submitted"
            again = await r2.resume_job("J-104", {"action": "approve"})   # double-click / replay
            assert again.status == "submitted"
            history = await r2.history("J-104")
            assert len(history) > 5                                   # replayable checkpoints
    assert len(backend.submissions) == 1


@pytest.mark.parametrize("persona_floor", [5000])
async def test_floor_above_budget_is_explained(tmp_path, persona_floor):
    async with harness(tmp_path) as r:
        r.persona = {**r.persona, "floor_usd": persona_floor}
        res = await r.start_job("J-100")
        assert res.state["price_quote"]["amount"] == persona_floor
        assert any("floor" in x for x in res.state["price_quote"]["rationale"])
