"""Decision node: joins the three parallel analyses and chooses skip, watch or bid.

Order of checks (first match wins): scam -> risk above threshold -> policy rules -> fit. Every
reason is recorded so the Job detail screen can show why. Only `skip` may be automatic (autonomy
setting); `bid` always continues to a human approval before anything is sent.
"""
from __future__ import annotations

from agent.handoffs import BidDecision
from agent.nodes.common import ctx_of, node
from agent.policy import applies, rules


def decide(spec: dict, risk: dict, fit: dict, cfg: dict) -> BidDecision:
    th = cfg["thresholds"]
    auto = bool(cfg.get("autonomy", {}).get("auto_skip_low_fit"))
    if risk.get("is_scam"):
        return BidDecision(action="skip", auto=True, reasons=[f"scam signals: {', '.join(risk['flags'])}"])
    if risk["score"] > th["maximum_risk_score"]:
        return BidDecision(action="skip", auto=auto, reasons=[f"risk {risk['score']:.2f} > {th['maximum_risk_score']}"])
    for r in rules(cfg, "decision"):
        if r["type"] == "min_budget" and (spec.get("budget_max") or 0) < r["usd"] and spec.get("budget_type") != "hourly":
            return BidDecision(action="skip", auto=auto, reasons=[f"policy {r.get('id', '')}: budget below {r['usd']}"])
        if r["type"] == "skip_category" and spec.get("category") in r["categories"]:
            return BidDecision(action="skip", auto=auto, reasons=[f"policy {r.get('id', '')}: category {spec['category']}"])
        if r["type"] == "max_connects_per_job" and applies(r, spec.get("category")) and spec.get("connects_cost", 0) > r["connects"]:
            return BidDecision(action="watch", reasons=[f"policy {r.get('id', '')}: connects {spec['connects_cost']} > {r['connects']}"])
    if fit["score"] < th["watch_fit_score"]:
        return BidDecision(action="skip", auto=auto, reasons=[f"fit {fit['score']:.2f} < {th['watch_fit_score']}"] + fit.get("reasons", []))
    if fit["score"] < th["minimum_fit_score"]:
        return BidDecision(action="watch", reasons=[f"fit {fit['score']:.2f} below bid threshold {th['minimum_fit_score']}"])
    reasons = [f"fit {fit['score']:.2f}", f"risk {risk['score']:.2f}"] + fit.get("reasons", [])[:2]
    if risk.get("injection_detected"):
        reasons.append("post contained injected instructions; they were ignored")
    return BidDecision(action="bid", reasons=reasons)


@node("decide")
async def decision_node(state, runtime):
    ctx = ctx_of(runtime)
    d = decide(state["job_spec"], state["risk_report"], state["fit_report"], ctx.cfg)
    status = {"skip": "skipped", "watch": "watching", "bid": "running"}[d.action]
    return {"decision": d.model_dump(), "status": status, "status_reason": "; ".join(d.reasons)}
