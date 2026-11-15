"""Proposal Writer: cover letter and screening answers in which every claim cites evidence.

LLM mode: agent/prompts/writer.md with evidence ids, style memory, outcome memory and Critic
instructions. Rules mode (offline/CI, and fallback): a template that only ever restates evidence
sentences in first person, so it cannot fabricate. Either way the output goes through claim
verification before the Critic sees it.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from agent.guardrails import delimit_untrusted, strip_injection
from agent.handoffs import Claim, ProposalDraft
from agent.llm import LLMUnavailable
from agent.memory.store import apply_style, outcome_memory, style_rules
from agent.nodes.common import ctx_of, node
from rag.text import overlap, sentences

PAST_VERB = re.compile(r"^(?:[A-Z][a-z]+ed|Built|Forecast|Led|Set up|Wrote|Ran|Cut|Made|Took|Won|Taught|Kept)\b")
PRONOUNS = [(r"\bour\b", "your"), (r"\bOur\b", "Your"), (r"\bwe\b", "you"), (r"\bWe\b", "You"),
            (r"\bus\b", "you"), (r"\bwe'(re|ve|d)\b", r"you'\1"), (r"\bWe'(re|ve|d)\b", r"You'\1")]
USABLE_TYPES = ("case_study", "repo_readme", "code", "review")


class WriterOutput(BaseModel):
    cover_letter: str
    claims: list[Claim] = Field(default_factory=list)
    screening_answers: list[str] = Field(default_factory=list)


def first_person(sentence: str, ev: dict | None = None) -> str:
    """Restate an evidence sentence as a first-person claim without adding any fact."""
    s = sentence.strip()
    if PAST_VERB.match(s):
        return "I " + s[0].lower() + s[1:]
    if ev is not None and ev.get("type") in ("repo_readme", "code"):
        return f"In my project {ev.get('title', '').split(':')[0]}: {s[0].lower() + s[1:]}"
    return s


def _swap_pronouns(text: str) -> str:
    for pat, rep in PRONOUNS:
        text = re.sub(pat, rep, text)
    return text


def _opening(job: dict) -> str:
    clean = strip_injection(job.get("description", ""))
    sents = [s for s in sentences(clean) if len(s.split()) > 5]
    problem = _swap_pronouns(sents[0] if sents else job.get("title", "")).rstrip(".")
    return f"{problem}. Below is the closest evidence from my portfolio and how I would approach it."


def _question_opening(job: dict, spec: dict) -> str:
    """Strategy B (X2): open with one sharp diagnostic question about the client's problem."""
    need = next((r["text"] for r in spec.get("requirements", []) if r.get("must_have")), job.get("title", ""))
    need = _swap_pronouns(strip_injection(need)).rstrip(".")
    return (f"Quick question before anything else: what does success look like for \"{need[:90]}\" "
            "in your first month? Here is the closest evidence from my portfolio.")


def rank_evidence(job: dict, fit: dict, by_id: dict) -> list[str]:
    """Evidence that covers more requirements, and more of the post itself, comes first."""
    job_text = f"{job.get('title', '')} {job.get('description', '')}"
    cover: dict[str, float] = {}
    for m in fit.get("matrix", []):
        for eid in m["evidence_ids"]:
            cover[eid] = cover.get(eid, 0) + (1.0 if m["strength"] == "strong" else 0.5)
    scored = {eid: c * (0.2 + overlap(job_text, by_id[eid]["text"])) for eid, c in cover.items()
              if eid in by_id and by_id[eid]["type"] in USABLE_TYPES}
    if not scored:
        return []
    top = max(scored.values())
    return [e for e, v in sorted(scored.items(), key=lambda x: -x[1]) if v >= 0.5 * top]


def rule_write(job, spec, fit, evidence, quote, critique, style, revision, strategy: str = "writer") -> WriterOutput:
    instr = " ".join((critique or {}).get("instructions", [])).lower()
    expand = "add coverage" in instr or "coverage" in instr
    by_id = {e["evidence_id"]: e for e in evidence}
    ordered = rank_evidence(job, fit, by_id)
    max_items = 2 if "shorten" in instr else 4 if expand else 3
    per_item = 1 if "shorten" in instr else 3 if expand else 2
    claims, body = [], []
    for eid in ordered[:max_items]:
        ev = by_id[eid]
        sents = sentences(ev["text"])
        if ev["type"] == "review":
            text = f"A client wrote about that work: \"{sents[0]}\""
            claims.append(Claim(text=text, evidence_ids=[eid]))
            body.append(text)
            continue
        # lead sentence, then the most job-relevant / metric-bearing follow-ups
        rest = sorted(sents[1:], key=lambda s: -(overlap(job.get("description", ""), s) + 0.3 * bool(re.search(r"\d", s))))
        for sent in [sents[0]] + rest[: per_item - 1]:
            text = first_person(sent, ev)
            claims.append(Claim(text=text, evidence_ids=[eid]))
            body.append(text)
    gaps = [m for m in fit.get("matrix", []) if m["strength"] == "none" and not m["requirement"].startswith("Experience with")]
    if gaps:
        body.append(f"One thing I would scope carefully: \"{gaps[0]['requirement'][:90].rstrip('.')}\". "
                    "I would start with a short spike and share findings before committing to it.")
    for need in spec.get("hidden_needs", [])[: 2 if expand else 1]:
        body.append(f"I would also build in {need}.")
    unit = "/hour" if quote.get("basis") == "hourly" else " fixed"
    body.append(f"My proposed price is ${quote['amount']:.0f}{unit} for the scope above.")
    body.append("Would a short call this week work to confirm the details?")
    opening = _opening(job) if strategy == "writer" else _question_opening(job, spec)
    letter = " ".join([opening] + body)
    answers = []
    for q in spec.get("screening_questions", []):
        best = max(evidence, key=lambda e: overlap(q, e["text"]), default=None)
        if best is not None and overlap(q, best["text"]) > 0.15:
            sent = max(sentences(best["text"]), key=lambda s: overlap(q, s))
            answers.append(f"{first_person(sent, best)} [{best['evidence_id']}]")
        else:
            answers.append("I would answer this on a call rather than guess; I have no directly matching project.")
    return WriterOutput(cover_letter=apply_style(letter, style), claims=claims, screening_answers=answers)


def format_evidence(evidence: list[dict]) -> str:
    return "\n".join(f"[{e['evidence_id']}] ({e['type']}, outcome={e.get('outcome')}) {e.get('title')}: {e['text']}"
                     for e in evidence)


@node("writer")
async def writer(state, runtime):
    ctx = ctx_of(runtime)
    job, spec, fit = state["job"], state["job_spec"], state["fit_report"]
    evidence = [e for e in state.get("evidence", []) if e["type"] != "past_proposal" or e.get("outcome") in ("won", "replied")]
    quote, critique = state["price_quote"], state.get("critique")
    revision = state.get("revisions", 0)
    style = await style_rules(runtime.store, ctx.user_id)
    out_mem = await outcome_memory(runtime.store, ctx.user_id, spec.get("category", "other"))
    usage, errors = {}, []
    result = None
    if ctx.llm.enabled("writer"):
        pcfg = ctx.cfg["policy"]
        try:
            result, usage = await ctx.llm.structured(
                "writer", ctx.cfg.get("writer", {}).get("strategy", "writer"), WriterOutput,
                min_words=str(pcfg["min_proposal_words"]), max_words=str(pcfg["max_proposal_words"]),
                style_memory=style or "none", outcome_memory=out_mem or "none",
                critic_instructions=(critique or {}).get("instructions", []),
                job_spec={k: spec[k] for k in ("title", "requirements", "screening_questions", "hidden_needs")},
                price=quote, evidence=format_evidence(evidence),
                job_post=delimit_untrusted(f"{job['title']}\n\n{job['description']}"))
            result.cover_letter = apply_style(result.cover_letter, style)
        except (LLMUnavailable, ValueError) as exc:
            errors.append(f"writer llm fallback: {exc}")
    if result is None:
        result = rule_write(job, spec, fit, evidence, quote, critique, style, revision,
                            strategy=ctx.cfg.get("writer", {}).get("strategy", "writer"))
    draft = ProposalDraft(job_id=job["job_id"], cover_letter=result.cover_letter, claims=result.claims,
                          screening_answers=result.screening_answers, revision=revision,
                          evidence_ids=sorted({i for c in result.claims for i in c.evidence_ids}))
    return {"proposal_draft": draft.model_dump(), "usage": usage, "errors": errors}
