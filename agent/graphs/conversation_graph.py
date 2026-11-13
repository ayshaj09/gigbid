"""Conversation graph (C1): one thread per client conversation.

    START -> load_thread -> classify_intent -> (interview_request) propose_slots -> draft_reply
                                            -> (other intents)                    -> draft_reply
          -> reply_approval_prep (dry_run) -> reply_approval (interrupt) -> approve: send_reply -> END
                                                                       -> edit changed by compliance: re-ask
                                                                       -> reject: END
Scam signals still get a drafted on-platform reply, but nothing is sent without approval.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agent.graphs.bid_graph import MARKET_RETRY
from agent.nodes.client_liaison import (
    classify_intent,
    draft_reply,
    load_thread,
    propose_slots,
    reply_approval,
    reply_approval_prep,
    send_reply,
)
from agent.nodes.common import TERMINAL, GigBidContext
from agent.state import ConversationState


def _g(nxt):
    return lambda s: END if s.get("status") in TERMINAL else nxt


def after_intent(state):
    if state.get("status") in TERMINAL:
        return END
    return "propose_slots" if state["intent"]["intent"] == "interview_request" else "draft_reply"


def after_reply_approval(state):
    return {"approved": "send_reply", "awaiting_approval": "reply_approval"}.get(state.get("status"), END)


def build_conversation_graph():
    g = StateGraph(ConversationState, context_schema=GigBidContext)
    g.add_node("load_thread", load_thread, retry_policy=MARKET_RETRY)
    g.add_node("classify_intent", classify_intent)
    g.add_node("propose_slots", propose_slots)
    g.add_node("draft_reply", draft_reply)
    g.add_node("reply_approval_prep", reply_approval_prep, retry_policy=MARKET_RETRY)
    g.add_node("reply_approval", reply_approval)
    g.add_node("send_reply", send_reply, retry_policy=MARKET_RETRY)
    g.add_edge(START, "load_thread")
    g.add_conditional_edges("load_thread", _g("classify_intent"), ["classify_intent", END])
    g.add_conditional_edges("classify_intent", after_intent, ["propose_slots", "draft_reply", END])
    g.add_conditional_edges("propose_slots", _g("draft_reply"), ["draft_reply", END])
    g.add_conditional_edges("draft_reply", _g("reply_approval_prep"), ["reply_approval_prep", END])
    g.add_conditional_edges("reply_approval_prep", _g("reply_approval"), ["reply_approval", END])
    g.add_conditional_edges("reply_approval", after_reply_approval, ["send_reply", "reply_approval", END])
    g.add_edge("send_reply", END)
    return g


def compile_conversation_graph(checkpointer=None, store=None):
    return build_conversation_graph().compile(checkpointer=checkpointer, store=store, name="conversation_graph")
