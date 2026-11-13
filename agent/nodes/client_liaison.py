"""Client Liaison (conversation graph): read new messages, classify intent, draft a reply or
interview slots, re-check with Compliance, and wait for approval before sending."""
from __future__ import annotations

import re
from datetime import datetime

from langgraph.types import interrupt
from pydantic import BaseModel

from agent.guardrails import delimit_untrusted, detect_injection
from agent.handoffs import ApprovalDecision, MessageIntent, ReplyDraft
from agent.llm import LLMUnavailable
from agent.marketplace_port import idempotency_key
from agent.memory.store import apply_style, record_edit, style_rules
from agent.nodes.common import ctx_of, node
from agent.nodes.compliance import check

SCAM = re.compile(r"outside (?:the )?(?:platform|upwork)|whats\s?app|telegram|email me|e-?mail at|pay (?:you )?directly|"
                  r"save fees|crypto|gift card|cheque|check deposit|bank details|password|\b[\w.+-]+@[\w-]+\.\w+", re.I)
INTERVIEW = re.compile(r"\b(?:call|interview|meet|meeting|chat|zoom|google meet|teams|schedule|available)\b", re.I)
NEGOTIATE = re.compile(r"\$\s?\d|\b(?:rate|price|budget|discount|cheaper|lower|reduce|per hour|/hour|/hr)\b", re.I)


class LiaisonReply(BaseModel):
    text: str


def classify(text: str) -> MessageIntent:
    inj = bool(detect_injection(text))
    if SCAM.search(text):
        return MessageIntent(intent="scam_signal", confidence=0.9, injection_detected=inj,
                             notes="off-platform contact/payment or credential request")
    if INTERVIEW.search(text):
        return MessageIntent(intent="interview_request", confidence=0.8, injection_detected=inj)
    if NEGOTIATE.search(text):
        return MessageIntent(intent="negotiation", confidence=0.7, injection_detected=inj)
    if "?" in text:
        return MessageIntent(intent="question", confidence=0.6, injection_detected=inj)
    return MessageIntent(intent="other", confidence=0.4, injection_detected=inj)


def rule_reply(intent: str, msg: str, slots: list[str], floor: float, rate: float, has_negotiation: bool) -> str:
    parts = ["Thanks for getting back to me."]
    if intent == "scam_signal":
        parts.append("To keep us both protected I keep all communication and payment on the platform, "
                     "so let's continue here.")
    if intent == "interview_request" or INTERVIEW.search(msg):
        nice = [datetime.fromisoformat(s).strftime("%a %d %b, %H:%M") for s in slots]  # no digit runs: PII masks
        parts.append("I'd be glad to talk. These times work for me: " + "; ".join(nice) + ". Which suits you?")
    if has_negotiation or intent == "negotiation":
        parts.append(f"On price, I can't go below ${floor:.0f}/hour for this scope, because it includes the "
                     "monitoring and retries that stop silent failures; I'm happy to trim scope to fit a budget instead.")
    if intent in ("question", "other"):
        parts.append("Good question. I'll answer it properly here; let me know if more detail on any point helps.")
    return " ".join(parts)


@node("load_thread", kind="conversation")
async def load_thread(state, runtime):
    ctx = ctx_of(runtime)
    msgs = await ctx.marketplace("client_liaison").list_messages(state["thread_id"])
    client_msgs = [m for m in msgs if m["sender"] == "client"]
    return {"messages": msgs, "last_client_message": client_msgs[-1] if client_msgs else {}, "status": "running"}


@node("classify_intent", kind="conversation")
async def classify_intent(state, runtime):
    ctx = ctx_of(runtime)
    text = state.get("last_client_message", {}).get("text", "")
    if not text:
        return {"status": "skipped", "status_reason": "no client message to answer"}
    intent, usage = classify(text), {}
    if ctx.llm.enabled("intent"):
        try:
            llm_int, usage = await ctx.llm.structured(
                "intent", "intent", MessageIntent, history=[m["text"][:200] for m in state["messages"][-6:]],
                message=delimit_untrusted(text, "client_message"))
            if intent.intent != "scam_signal":  # rules can't be overridden on scam signals
                intent = llm_int
        except (LLMUnavailable, ValueError):
            pass
    return {"intent": intent.model_dump(), "usage": usage}


@node("propose_slots", kind="conversation")
async def propose_slots(state, runtime):
    ctx = ctx_of(runtime)
    res = await ctx.tools("client_liaison")("free_slots", {"days": 5, "duration_min": 30})
    return {"proposed_slots": [s["start"] for s in res["slots"]]}


@node("draft_reply", kind="conversation")
async def draft_reply(state, runtime):
    ctx = ctx_of(runtime)
    msg = state["last_client_message"]["text"]
    intent = state["intent"]["intent"]
    slots = state.get("proposed_slots", [])
    style = await style_rules(runtime.store, ctx.user_id)
    floor = ctx.persona.get("hourly_rate_usd", 0)
    text, usage = None, {}
    if ctx.llm.enabled("client_liaison"):
        try:
            out, usage = await ctx.llm.structured(
                "client_liaison", "client_liaison", LiaisonReply, slots=slots, floor=str(floor),
                style_memory=style or "none", intent=intent, job=state.get("job_id", ""), evidence="",
                history=[m["text"][:200] for m in state["messages"][-6:]],
                message=delimit_untrusted(msg, "client_message"))
            text = out.text
        except (LLMUnavailable, ValueError):
            text = None
    if text is None:
        text = rule_reply(intent, msg, slots, floor, floor, bool(NEGOTIATE.search(msg)))
    verdict = check(apply_style(text, style), ctx.cfg, None, msg, min_words=1)
    draft = ReplyDraft(thread_id=state["thread_id"], text=verdict.cleaned_text, proposed_slots=slots)
    out = {"reply_draft": draft.model_dump(), "compliance_verdict": verdict.model_dump(), "usage": usage}
    if not verdict.allowed:
        out.update(status="blocked", status_reason="; ".join(verdict.violations))
    return out


@node("reply_approval_prep", kind="conversation")
async def reply_approval_prep(state, runtime):
    ctx = ctx_of(runtime)
    d = state["reply_draft"]
    key = idempotency_key(ctx.user_id, state["thread_id"], d["text"])
    preview = await ctx.marketplace("preview").send_message(state["thread_id"], d["text"], key, dry_run=True)
    return {"dry_run_preview": preview, "status": "awaiting_approval"}


@node("reply_approval", kind="conversation")
async def reply_approval(state, runtime):
    ctx = ctx_of(runtime)
    decision = ApprovalDecision.model_validate(interrupt({
        "kind": "message", "thread_id": state["thread_id"], "client_message": state["last_client_message"],
        "intent": state["intent"], "draft": state["reply_draft"], "compliance": state.get("compliance_verdict"),
        "dry_run_preview": state.get("dry_run_preview"), "actions": ["approve", "edit", "reject"]}))
    if decision.action == "reject":
        return {"approval": decision.model_dump(), "status": "rejected", "status_reason": decision.reason or ""}
    draft = dict(state["reply_draft"])
    if decision.action == "edit" and decision.edited_text:
        if runtime.store is not None:
            await record_edit(runtime.store, ctx.user_id, draft["text"], decision.edited_text, ctx.cfg)
        verdict = check(decision.edited_text, ctx.cfg, None, state["last_client_message"].get("text", ""), min_words=1)
        draft["text"] = verdict.cleaned_text
        if not verdict.allowed or verdict.cleaned_text != " ".join(decision.edited_text.split()):
            return {"approval": {**decision.model_dump(), "needs_reapproval": True}, "reply_draft": draft,
                    "compliance_verdict": verdict.model_dump(), "status": "awaiting_approval"}
    return {"approval": decision.model_dump(), "reply_draft": draft, "status": "approved"}


@node("send_reply", kind="conversation")
async def send_reply(state, runtime):
    ctx = ctx_of(runtime)
    d = state["reply_draft"]
    key = idempotency_key(ctx.user_id, state["thread_id"], d["text"])
    res = await ctx.marketplace("liaison_send").send_message(state["thread_id"], d["text"], key, dry_run=False)
    return {"sent": res, "status": "sent"}
