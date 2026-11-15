"""Risk Assessor: client quality from marketplace history; flags scams, free-work requests,
off-platform asks and injected instructions.

Rules are authoritative for scam flags: an LLM (if configured) may ADD flags but can never remove a
rule-detected one, so a persuasive job post cannot talk its way past the guard.
"""
from __future__ import annotations

import re

from agent.guardrails import delimit_untrusted, detect_injection, find_contact_details
from agent.handoffs import RiskReport
from agent.llm import LLMUnavailable
from agent.nodes.common import ctx_of, node

PATTERNS = {
    "unpaid_work": r"\bfor free\b|\bunpaid\b|\bfree (?:test|trial|sample)\b|\bno pay\b|\bwithout pay",
    "off_platform_contact": r"whats\s?app|telegram|skype|signal\b|\bwechat|contact me (?:on|at|via)|email me",
    "off_platform_payment": r"\bcrypto|bitcoin|usdt|gift ?cards?|outside (?:the )?(?:platform|upwork)|pay (?:you )?directly|paypal|western union",
    "credential_request": r"bank details|\bpassword|\bid (?:card|for verification)|\bssn\b|send (?:me )?your (?:id|passport)|for verification",
    "vague_scope": r"^.{0,80}$",
}
SCAM_FLAGS = {"unpaid_work", "off_platform_contact", "off_platform_payment", "credential_request"}
SEVERITY = {"unpaid_work": 0.8, "off_platform_contact": 0.7, "off_platform_payment": 0.9, "credential_request": 0.95,
            "prompt_injection": 0.3, "poor_client": 0.4, "vague_scope": 0.25, "zero_budget": 0.6, "unspecified_rate": 0.1}


def risk_rules(cfg: dict) -> tuple[dict, dict, set]:
    """Defaults above, overridden/extended by `risk:` in agent/config.yaml (patterns, severity,
    scam_flags), so a new scam pattern is a config edit, not a code change."""
    rc = cfg.get("risk") or {}
    patterns = {**PATTERNS, **(rc.get("patterns") or {})}
    severity = {**SEVERITY, **(rc.get("severity") or {})}
    return patterns, severity, SCAM_FLAGS | set(rc.get("scam_flags") or [])


def client_quality(h: dict) -> float:
    if not h:
        return 0.3
    q = 0.25 * bool(h.get("payment_verified"))
    posted, hires = h.get("jobs_posted") or 0, h.get("hires") or 0
    q += 0.25 * (min(1.0, hires / posted) if posted else 0.0)
    rating = h.get("average_rating")
    q += 0.25 * ((rating - 1) / 4 if rating else 0.4)
    q += 0.25 * min(1.0, (h.get("total_spent_usd") or 0) / 10000)
    return round(q, 3)


def rule_risk(job: dict, history: dict, cfg: dict) -> RiskReport:
    patterns, severity, scam_flags = risk_rules(cfg)
    text = f"{job.get('title', '')}\n{job.get('description', '')}"
    flags = [f for f, pat in patterns.items() if re.search(pat, job.get("description", "") if f == "vague_scope" else text, re.I)]
    if find_contact_details(job.get("description", "")) and "off_platform_contact" not in flags:
        if any(k.startswith(("email", "phone")) for k in find_contact_details(job["description"])):
            flags.append("off_platform_contact")
    injected = detect_injection(text)
    if injected:
        flags.append("prompt_injection")
    budget = job.get("budget") or {}
    if budget and not budget.get("max"):
        # an hourly post without a stated range is normal on the platform; a fixed job with no budget is not
        flags.append("unspecified_rate" if budget.get("type") == "hourly" else "zero_budget")
    cq = client_quality(history)
    if cq < 0.35 or (history.get("average_rating") or 5) < cfg["thresholds"]["min_client_rating"]:
        flags.append("poor_client")
    score = max([severity.get(f, 0.3) for f in flags], default=0.0)
    score = min(1.0, score + (1 - cq) * 0.2)
    is_scam = bool(scam_flags & set(flags)) or ("zero_budget" in flags and "unpaid_work" in flags)
    expl = (f"Client quality {cq:.2f} (verified={history.get('payment_verified')}, hires={history.get('hires')}, "
            f"rating={history.get('average_rating')}). Flags: {', '.join(flags) or 'none'}.")
    if injected:
        expl += " The post contains text addressed to an AI; it is treated as data and ignored."
    return RiskReport(score=round(score, 3), flags=flags, client_quality=cq, injection_detected=bool(injected),
                      is_scam=is_scam, explanation=expl)


@node("risk_assessor")
async def risk_assessor(state, runtime):
    ctx = ctx_of(runtime)
    job = state["job"]
    history = {}
    if job.get("client_id"):
        history = await ctx.marketplace("risk_assessor").get_client_history(job["client_id"])
    report = rule_risk(job, history, ctx.cfg)
    usage = {}
    if ctx.llm.enabled("risk_assessor"):
        try:
            llm_report, usage = await ctx.llm.structured(
                "risk_assessor", "risk_assessor", RiskReport,
                job_post=delimit_untrusted(f"{job['title']}\n\n{job['description']}"),
                client_history=history, prechecks=report.flags)
            flags = sorted(set(report.flags) | set(llm_report.flags))
            report = report.model_copy(update={
                "flags": flags, "score": max(report.score, llm_report.score),
                "is_scam": report.is_scam or llm_report.is_scam,
                "explanation": report.explanation + " LLM: " + llm_report.explanation})
        except (LLMUnavailable, ValueError) as exc:
            return {"risk_report": report.model_dump(), "errors": [f"risk llm fallback: {exc}"]}
    return {"risk_report": report.model_dump(), "usage": usage}
