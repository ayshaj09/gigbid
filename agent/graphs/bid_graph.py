"""Bid graph (C1): one thread per job.

    START -> scout -> (Send) analyst | risk_assessor | fit_matcher   [parallel, reducers on shared keys]
          -> decide -> skip/watch: END
                    -> bid: pricing -> writer -> verify -> critic
                                         ^                    |  fail & revisions < max_revisions
                                         +--------------------+
                                       critic pass / limit -> compliance -> approval_prep -> approval (interrupt)
                                       approval: approve -> submit -> END
                                                 edit    -> (compliance re-check) -> submit | approval_prep
                                                 reject  -> END
Every edge checks the thread status, so budgets (needs_attention), errors (dead_letter) and
Compliance blocks stop the thread visibly instead of running on.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, Send

from agent.marketplace_port import MarketplaceUnavailable
from agent.nodes.analyst import analyst
from agent.nodes.approval import approval, approval_prep, submit
from agent.nodes.common import TERMINAL, GigBidContext
from agent.nodes.compliance import compliance
from agent.nodes.critic import critic
from agent.nodes.decision import decision_node
from agent.nodes.fit_matcher import fit_matcher
from agent.nodes.pricing import pricing
from agent.nodes.risk_assessor import risk_assessor
from agent.nodes.scout import scout_intake
from agent.nodes.verifier import verifier
from agent.nodes.writer import writer
from agent.state import BidState

# Transient marketplace errors are retried by LangGraph itself (bounded, with backoff); if they
# persist, the exception surfaces and the runner parks the thread in degraded mode.
MARKET_RETRY = RetryPolicy(max_attempts=3, initial_interval=0.5, backoff_factor=2.0,
                           retry_on=lambda e: isinstance(e, MarketplaceUnavailable))


def _stop(state) -> bool:
    return state.get("status") in TERMINAL


def fan_out(state):
    if _stop(state):
        return END
    return [Send("analyst", state), Send("risk_assessor", state), Send("fit_matcher", state)]


def after_decide(state):
    return END if _stop(state) or state["decision"]["action"] != "bid" else "pricing"


def after_critic(state, max_revisions: int):
    """`revisions` counts failed critiques: rewrite while revisions <= max_revisions (so at most
    `max_revisions` rewrites), then go on to Compliance with the unresolved critique attached."""
    if _stop(state):
        return END
    if not state["critique"]["passed"] and state.get("revisions", 0) <= max_revisions:
        return "writer"
    return "compliance"


def after_approval(state):
    status = state.get("status")
    if status == "approved":
        return "submit"
    if status == "awaiting_approval":
        return "approval"   # compliance changed the user's edit: show it again
    return END


def guard(nxt: str):
    return lambda s: END if _stop(s) else nxt


def build_bid_graph(max_revisions: int = 2):
    g = StateGraph(BidState, context_schema=GigBidContext)
    g.add_node("scout", scout_intake, retry_policy=MARKET_RETRY)
    g.add_node("analyst", analyst)
    g.add_node("risk_assessor", risk_assessor, retry_policy=MARKET_RETRY)
    g.add_node("fit_matcher", fit_matcher, retry_policy=MARKET_RETRY)
    g.add_node("decide", decision_node)
    g.add_node("pricing", pricing, retry_policy=MARKET_RETRY)
    g.add_node("writer", writer)
    g.add_node("verify", verifier)
    g.add_node("critic", critic)
    g.add_node("compliance", compliance)
    g.add_node("approval_prep", approval_prep, retry_policy=MARKET_RETRY)
    g.add_node("approval", approval)
    g.add_node("submit", submit, retry_policy=MARKET_RETRY)

    g.add_edge(START, "scout")
    g.add_conditional_edges("scout", fan_out, ["analyst", "risk_assessor", "fit_matcher", END])
    g.add_edge(["analyst", "risk_assessor", "fit_matcher"], "decide")   # join: waits for all three
    g.add_conditional_edges("decide", after_decide, ["pricing", END])
    g.add_conditional_edges("pricing", guard("writer"), ["writer", END])
    g.add_conditional_edges("writer", guard("verify"), ["verify", END])
    g.add_conditional_edges("verify", guard("critic"), ["critic", END])
    g.add_conditional_edges("critic", lambda s: after_critic(s, max_revisions), ["writer", "compliance", END])
    g.add_conditional_edges("compliance", guard("approval_prep"), ["approval_prep", END])
    g.add_conditional_edges("approval_prep", guard("approval"), ["approval", END])
    g.add_conditional_edges("approval", after_approval, ["submit", "approval", END])
    g.add_edge("submit", END)
    return g


def compile_bid_graph(checkpointer=None, store=None, max_revisions: int = 2):
    return build_bid_graph(max_revisions).compile(checkpointer=checkpointer, store=store, name="bid_graph")
