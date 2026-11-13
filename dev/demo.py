"""One job from inbox to approved proposal, one scam skipped, one injection ignored, one client reply,
all through the real graphs and in-memory MCP servers. Human approval is asked on the console.

    python -m dev.demo            # interactive: approve / edit / reject
    python -m dev.demo --yes      # approve everything (CI smoke)
    MODEL_PROFILE=open OPEN_MODEL_BASE_URL=http://localhost:11434/v1 python -m dev.demo   # with Ollama
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import tempfile
import textwrap

from agent.testing import harness


def show(title, text):
    print(f"\n=== {title} ===")
    print(textwrap.fill(text, 100))


def ask(auto: bool) -> dict:
    if auto:
        return {"action": "approve"}
    choice = input("\n[a]pprove / [e]dit / [r]eject? ").strip().lower()[:1]
    if choice == "e":
        return {"action": "edit", "edited_text": input("Paste edited text:\n")}
    if choice == "r":
        return {"action": "reject", "reason": input("Reason: ")}
    return {"action": "approve"}


async def main(auto: bool, profile: str | None):
    over = {"models": {"profile": profile}} if profile else None
    with tempfile.TemporaryDirectory() as tmp:
        async with harness(tmp, cfg_overrides=over) as r:
            async def progress(ev):
                print(f"  - {ev['node']:<14} {ev['status'] or ''}")

            for jid in ("J-101", "J-102"):
                print(f"\n>>> Job {jid}")
                res = await r.start_job(jid, stream_cb=progress)
                print("  status:", res.status, "|", (res.state.get("status_reason") or "")[:140])
                print("  risk flags:", res.state["risk_report"]["flags"])

            print("\n>>> Job J-100 (inbox -> proposal)")
            res = await r.start_job("J-100", stream_cb=progress)
            p = res.interrupt
            show("Draft proposal", p["draft"]["cover_letter"])
            print("\nClaims and evidence:")
            for c in p["claims"]:
                print(f"  [{c['label']}] {c['claim'][:80]}... <- {[e['id'] for e in c['evidence']]}")
            print("Price:", p["price_quote"]["amount"], "|", "; ".join(p["price_quote"]["rationale"]))
            print("Dry run:", p["dry_run_preview"]["cost_connects"], "connects, balance after",
                  p["dry_run_preview"]["connects_balance_after"])
            res = await r.resume_job("J-100", ask(auto), stream_cb=progress)
            while res.status == "awaiting_approval":
                show("Compliance changed your edit", res.interrupt["draft"]["cover_letter"])
                res = await r.resume_job("J-100", ask(auto))
            print("  final status:", res.status, res.state.get("submission", {}).get("proposal_id", ""))

            print("\n>>> Client replied on thread T-1")
            conv = await r.start_conversation("T-1", "J-100", stream_cb=progress)
            show(f"Suggested reply ({conv.state['intent']['intent']})", conv.interrupt["draft"]["text"])
            conv = await r.resume_conversation("T-1", ask(auto))
            print("  final status:", conv.status)


if __name__ == "__main__":
    logging.getLogger("mcp").setLevel(logging.WARNING)
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--profile", default=None)
    a = ap.parse_args()
    asyncio.run(main(a.yes, a.profile))
