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
from functools import lru_cache

import yaml

from agent.config import ROOT
from rag.text import overlap

STRONG, PARTIAL = 0.5, 0.25


@lru_cache(maxsize=4)
def taxonomy(path: str = "data/taxonomy/skills.yaml") -> tuple[dict, dict]:
    p = ROOT / path
    if not p.exists():
        return {}, {}
    t = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return ({k.lower(): v.lower() for k, v in (t.get("aliases") or {}).items()},
            {k.lower(): {x.lower() for x in v} for k, v in (t.get("implies") or {}).items()})


def canon(skill: str) -> str:
    s = skill.strip().lower()
    return taxonomy()[0].get(s, s)


def expand_skills(portfolio_skills: set[str]) -> tuple[set[str], set[str]]:
    """(direct, implied): canonical portfolio skills, plus umbrella skills implied by them."""
    direct = {canon(s) for s in portfolio_skills}
    implied = {u for u, specific in taxonomy()[1].items() if specific & direct} - direct
    return direct, implied


def strength(req_text: str, ev: dict, req_skills: list[str] | None = None) -> float:
    """Lexical coverage of the requirement by the evidence text; a requirement naming a skill is also
    strong when the evidence item is TAGGED with that skill, directly or as an umbrella the taxonomy
    derives from its specific tags (a churn model tagged XGBoost proves "Machine Learning")."""
    lex = overlap(req_text, f"{ev.get('title', '')} {ev['text']} {' '.join(ev.get('skills', []))}")
    if req_skills:
        direct, implied = expand_skills(set(ev.get("skills", [])))
        if any(canon(s) in direct | implied for s in req_skills):
            return max(lex, STRONG)
    return lex


PROOF_TYPES = {"case_study", "repo_readme", "code", "review", "cv"}  # past proposals are claims, not proof


def build_fit(reqs, items: list[dict], per_req: dict[str, list], weak: list[str], portfolio_skills: set[str],
              required_skills: list[str]) -> FitReport:
    by_id = {i["evidence_id"]: i for i in items if i["type"] in PROOF_TYPES}
    matrix, total, got = [], 0.0, 0.0
    for r in reqs:
        cand_ids = [e for e, _ in per_req.get(r.id, [])] or list(by_id)
        scored = sorted(((strength(r.text + " " + " ".join(r.skills), by_id[e], r.skills), e) for e in cand_ids if e in by_id),
                        reverse=True)
        good = [e for s, e in scored if s >= PARTIAL][:3]
        best = scored[0][0] if scored else 0.0
        level = "none" if r.id in weak or best < PARTIAL else "strong" if best >= STRONG else "partial"
        matrix.append(RequirementMatch(requirement_id=r.id, requirement=r.text,
                                       evidence_ids=good if level != "none" else [], strength=level))
        w = 1.0 if r.must_have else 0.4
        total += w
        got += w * {"strong": 1.0, "partial": 0.5, "none": 0.0}[level]
    direct, implied = expand_skills(portfolio_skills)
    matched = [s for s in required_skills if canon(s) in direct | implied]
    missing = [s for s in required_skills if canon(s) not in direct | implied]
    implied_hits = [s for s in matched if canon(s) not in direct]
    req_score = got / total if total else 0.0
    skill_score = len(matched) / len(required_skills) if required_skills else req_score
    score = round(0.6 * req_score + 0.4 * skill_score, 3)
    reasons = [f"{sum(m.strength == 'strong' for m in matrix)}/{len(matrix)} requirements strongly evidenced",
               f"skills matched: {', '.join(matched) or 'none'}"]
    if missing:
        reasons.append(f"no evidence for: {', '.join(missing)}")
    if implied_hits:
        reasons.append(f"implied by specific skills (taxonomy): {', '.join(implied_hits)}")
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
