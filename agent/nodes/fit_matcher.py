"""Fit Matcher: map every requirement to portfolio evidence (through the Portfolio MCP server's
`match_requirements` tool) and produce a fit score with reasons and a requirement-to-evidence matrix.

Strength per requirement is judged on the evidence text itself (stemmed coverage of the
requirement), independent of the retrieval variant's score scale, so the fit score is comparable
across variants.
"""
from __future__ import annotations

from agent.handoffs import FitReport, RequirementMatch
from agent.nodes.analyst import extract_requirements
from agent.nodes.common import ctx_of, node
from rag.text import overlap

STRONG, PARTIAL = 0.5, 0.25


def strength(req_text: str, ev: dict) -> float:
    return overlap(req_text, f"{ev.get('title', '')} {ev['text']} {' '.join(ev.get('skills', []))}")


PROOF_TYPES = {"case_study", "repo_readme", "code", "review", "cv"}  # past proposals are claims, not proof


def build_fit(reqs, items: list[dict], per_req: dict[str, list], weak: list[str], portfolio_skills: set[str],
              required_skills: list[str]) -> FitReport:
    by_id = {i["evidence_id"]: i for i in items if i["type"] in PROOF_TYPES}
    matrix, total, got = [], 0.0, 0.0
    for r in reqs:
        cand_ids = [e for e, _ in per_req.get(r.id, [])] or list(by_id)
        scored = sorted(((strength(r.text + " " + " ".join(r.skills), by_id[e]), e) for e in cand_ids if e in by_id),
                        reverse=True)
        good = [e for s, e in scored if s >= PARTIAL][:3]
        best = scored[0][0] if scored else 0.0
        level = "none" if r.id in weak or best < PARTIAL else "strong" if best >= STRONG else "partial"
        matrix.append(RequirementMatch(requirement_id=r.id, requirement=r.text,
                                       evidence_ids=good if level != "none" else [], strength=level))
        w = 1.0 if r.must_have else 0.4
        total += w
        got += w * {"strong": 1.0, "partial": 0.5, "none": 0.0}[level]
    lower_skills = {s.lower() for s in portfolio_skills}
    matched = [s for s in required_skills if s.lower() in lower_skills]
    missing = [s for s in required_skills if s.lower() not in lower_skills]
    req_score = got / total if total else 0.0
    skill_score = len(matched) / len(required_skills) if required_skills else req_score
    score = round(0.6 * req_score + 0.4 * skill_score, 3)
    reasons = [f"{sum(m.strength == 'strong' for m in matrix)}/{len(matrix)} requirements strongly evidenced",
               f"skills matched: {', '.join(matched) or 'none'}"]
    if missing:
        reasons.append(f"no evidence for: {', '.join(missing)}")
    return FitReport(score=score, matched_skills=matched, missing_skills=missing,
                     evidence_ids=sorted({e for m in matrix for e in m.evidence_ids}), matrix=matrix, reasons=reasons)


@node("fit_matcher")
async def fit_matcher(state, runtime):
    ctx = ctx_of(runtime)
    job = state["job"]
    reqs = extract_requirements(job)
    call = ctx.tools("fit_matcher")
    res = await call("match_requirements", {
        "requirements": [{"id": r.id, "text": r.text, "skills": r.skills} for r in reqs],
        "job_text": f"{job['title']}. {job['description']}", "k": ctx.cfg["retrieval"].get("k", 8)})
    skills = await call("list_skills", {})
    items = res["items"]
    per_req = {h["requirement_id"]: [tuple(x) for x in h["evidence"]] for h in res["per_requirement"]}
    report = build_fit(reqs, items, per_req, res["weak_requirements"], {s["skill"] for s in skills["skills"]},
                       job.get("required_skills", []))
    return {"fit_report": report.model_dump(), "evidence": items,
            "trace": [{"node": "fit_matcher", "variant": res["variant"], "weak": res["weak_requirements"]}]}
