from agent.testing import harness
from mcp_servers.marketplace.adapters.gigsim import FixtureGigSim


async def test_interview_request_offers_slots_and_sends_after_approval(tmp_path):
    backend = FixtureGigSim()
    async with harness(tmp_path, backend=backend) as r:
        res = await r.start_conversation("T-1", "J-100")
        assert res.status == "awaiting_approval"
        assert res.state["intent"]["intent"] == "interview_request"
        assert res.state["proposed_slots"] and "these times" in res.interrupt["draft"]["text"].lower()
        from datetime import datetime
        first = datetime.fromisoformat(res.state["proposed_slots"][0]).strftime("%H:%M")
        assert first in res.interrupt["draft"]["text"]       # slots survive compliance/PII masking
        assert backend.sent_messages == []
        done = await r.resume_conversation("T-1", {"action": "approve"})
        assert done.status == "sent" and len(backend.sent_messages) == 1


async def test_scam_signal_reply_stays_on_platform(tmp_path):
    backend = FixtureGigSim()
    async with harness(tmp_path, backend=backend) as r:
        res = await r.start_conversation("T-2", "J-104")
        assert res.state["intent"]["intent"] == "scam_signal"
        text = res.interrupt["draft"]["text"].lower()
        assert "on the platform" in text and "@" not in text
        assert "$40/hour" in text                       # negotiation answered at the floor
        rej = await r.resume_conversation("T-2", {"action": "reject", "reason": "report client instead"})
        assert rej.status == "rejected" and backend.sent_messages == []
