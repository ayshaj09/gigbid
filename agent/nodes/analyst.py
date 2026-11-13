"""Job Analyst: extract a structured JobSpec (deliverables, skills, budget, timeline, screening
questions, hidden needs). LLM when configured for the node; deterministic rules otherwise or on
model failure. The job post reaches the LLM only inside a randomised untrusted-data fence."""
from __future__ import annotations

import re

from agent.guardrails import delimit_untrusted, detect_injection
from agent.handoffs import JobSpec, Requirement
from agent.llm import LLMUnavailable
from agent.nodes.common import ctx_of, node
from rag.text import sentences

NEED = re.compile(r"\b(?:need|needs|want|require|must|should|deliver|build|create|implement|fix|set up|migrate|"
                  r"move|extract|replace|we'?d like|looking for)\b", re.I)
NICE = re.compile(r"\bnice to have|bonus|plus\b|preferred|ideally\b", re.I)
HIDDEN = {
    r"retrain|monthly|ongoing": "repeatable retraining / handover documentation",
    r"fails silently|monitor": "monitoring and alerting",
    r"prove|evaluation|measure|accuracy report": "a measurable evaluation, not a demo",
    r"cpu|cheap|cost": "runs on modest hardware / cost-aware",
    r"maintain|our team|handover": "maintainable code the team can own",
}
CATEGORY_HINTS = {
    "ai_ml": ["machine learning", "ml ", "model", "rag", "llm", "chatbot", "classifier", "prediction", "nlp", "ocr"],
    "data_analysis": ["dashboard", "analytics", "sql", "excel", "report"],
    "web_fullstack": ["react", "next.js", "frontend", "backend", "api", "website"],
    "devops": ["docker", "celery", "kubernetes", "ci/cd", "etl", "pipeline", "cron"],
}


def extract_requirements(job: dict) -> list[Requirement]:
    """Deterministic decomposition shared by the Analyst and the Fit Matcher (which run in parallel,
    so the Fit Matcher cannot wait for the Analyst's output)."""
    reqs: list[Requirement] = []
    text = job.get("description", "")
    clean_sents = [s for s in sentences(text) if not detect_injection(s)]
    for s in clean_sents:
        if NEED.search(s) or len(clean_sents) <= 2:
            reqs.append(Requirement(id=f"r{len(reqs) + 1}", text=s[:300], must_have=not NICE.search(s)))
    covered = " ".join(r.text.lower() for r in reqs)
    for skill in job.get("required_skills", []):
        if skill.lower() not in covered:
            reqs.append(Requirement(id=f"r{len(reqs) + 1}", text=f"Experience with {skill}", skills=[skill]))
        else:
            for r in reqs:
                if skill.lower() in r.text.lower():
                    r.skills.append(skill)
                    break
    return reqs[:12]


def rule_spec(job: dict) -> JobSpec:
    text = job.get("description", "")
    budget = job.get("budget") or {}
    lower = (job.get("title", "") + " " + text).lower()
    category = job.get("category") or max(CATEGORY_HINTS, key=lambda c: sum(h in lower for h in CATEGORY_HINTS[c]))
    reqs = extract_requirements(job)
    return JobSpec(
        job_id=job["job_id"], title=job.get("title", ""), category=category,
        deliverables=[r.text for r in reqs if r.must_have and not r.text.startswith("Experience with")][:6],
        required_skills=job.get("required_skills", []), requirements=reqs,
        budget_min=budget.get("min"), budget_max=budget.get("max"),
        budget_type=budget.get("type", "fixed") if budget else "unknown",
        timeline_days=job.get("duration_days"), screening_questions=job.get("screening_questions", []),
        hidden_needs=[need for pat, need in HIDDEN.items() if re.search(pat, lower)],
        connects_cost=job.get("connects_cost", 0), client_id=job.get("client_id"),
    )


@node("analyst")
async def analyst(state, runtime):
    ctx = ctx_of(runtime)
    job = state["job"]
    spec = rule_spec(job)
    usage = {}
    if ctx.llm.enabled("analyst"):
        try:
            llm_spec, usage = await ctx.llm.structured(
                "analyst", "analyst", JobSpec,
                job_post=delimit_untrusted(f"{job['title']}\n\n{job['description']}", "job_post"),
                metadata={k: job.get(k) for k in ("job_id", "budget", "duration_days", "required_skills",
                                                  "screening_questions", "connects_cost", "client_id")},
            )
            # Trusted platform fields always come from the API, never from the model.
            spec = llm_spec.model_copy(update={
                "job_id": job["job_id"], "budget_min": spec.budget_min, "budget_max": spec.budget_max,
                "budget_type": spec.budget_type, "connects_cost": spec.connects_cost, "client_id": spec.client_id,
                "screening_questions": spec.screening_questions,
                "requirements": llm_spec.requirements or spec.requirements})
        except (LLMUnavailable, ValueError) as exc:
            return {"job_spec": spec.model_dump(), "errors": [f"analyst llm fallback: {exc}"]}
    return {"job_spec": spec.model_dump(), "usage": usage}
