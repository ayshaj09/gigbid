"""SILVER gold labels for the dev sets, from a fixed, documented rubric.

    python -m datapipe.silver_labels            # all personas
    python -m datapipe.apply_labels --persona X # human labels (CSV) then OVERRIDE silver ones

Why silver labels exist: the assignment's dev set is built here from Kaggle data, so there are no
instructor gold labels. Human labels are still the reference (fill label_decisions.csv /
label_relevance.csv); until then every metric computed on silver labels is reported as such
(`label_source` in gold.json, and the eval JSON carries `label_sources`).

Independence: this module imports nothing from agent/ or rag/. The rubric uses only the dataset's
own fields (category, skill tags, budget, scam label) and the persona's floor and rate, so the agent
cannot score well by copying the labeller's code. It does share one signal with the Fit Matcher,
skill overlap, which is the honest limitation: silver labels reward skill matching more than a human
would, and under-reward jobs whose skills are implied rather than named.

Rubric v2 (decision):
  scam label (fake_job_postings `fraudulent`=1)               -> skip
  category != persona category and skill overlap < 2          -> skip
  budget known and below the persona's floor/rate (see below)  -> skip
  overlap counts specific shared skills; all GENERIC tags together count as one
  same category and overlap >= 2                              -> bid
  same category and overlap == 1, or other category overlap >= 2 -> watch
  otherwise                                                   -> skip
  budget rule: fixed max < 0.5 * floor, or hourly max < 0.6 * persona rate
  planted-injection copies get the label of the job they were copied from.

Rubric v2 (evidence relevance): an evidence item is relevant to a non-scam job when its skill
tags share at least one skill with the job's required skills (case-insensitive, after aliasing),
or its title shares a non-trivial keyword with the job title.
Umbrella skills (IMPLIES) are granted to the persona from specific ones it demonstrably has, e.g.
PyTorch -> deep learning; the map is listed below and in docs/DATA_CARD.md.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUBRIC = "silver_rubric_v2"
ALIASES = {"artificial intelligence": "ai", "ml": "machine learning", "llms": "llm", "large language models": "llm",
           "natural language processing": "nlp", "reactjs": "react", "react.js": "react", "nodejs": "node.js",
           "postgresql": "sql", "postgres": "sql", "mysql": "sql", "microsoft excel": "excel", "microsoft power bi": "power bi",
           "data visualization": "data analysis", "data analytics": "data analysis", "web development": "full stack",
           "web application": "full stack", "python programming": "python"}
# Umbrella skills a human labeller would grant from specific ones (job tags are often the umbrella term).
IMPLIES = {
    "machine learning": {"scikit-learn", "xgboost", "lightgbm", "pytorch", "classification", "tensorflow"},
    "deep learning": {"pytorch", "transformers", "bert", "tensorflow", "yolo"},
    "ai": {"llm", "rag", "langchain", "openai api", "machine learning", "nlp", "computer vision"},
    "chatbot": {"llm", "rag", "langchain", "openai api"},
    "data science": {"pandas", "scikit-learn", "xgboost", "forecasting", "statistics"},
    "computer vision": {"opencv", "yolo"},
    "nlp": {"bert", "transformers", "topic modeling"},
    "frontend": {"react", "next.js", "typescript", "javascript", "tailwind"},
    "backend": {"fastapi", "django", "flask", "node.js", "express", "sql"},
    "full stack": {"react", "next.js", "node.js", "django", "fastapi"},
    "javascript": {"react", "next.js", "node.js", "typescript"},
    "data analysis": {"sql", "excel", "power bi", "tableau", "pandas", "google sheets"},
    "statistics": {"a/b testing", "regression"},
}
# Tags too generic to count as evidence of fit on their own ("AI" is on 3D-modelling posts too).
GENERIC = {"ai", "chatbot", "backend", "frontend", "full stack", "data analysis", "javascript"}
STOP = {"and", "for", "the", "with", "from", "need", "needed", "expert", "developer", "project", "help", "looking",
        "build", "create", "simple", "small", "data", "app", "web", "website"}


def _norm(s: str) -> str:
    s = s.strip().lower()
    return ALIASES.get(s, s)


def _skills(x) -> set[str]:
    if isinstance(x, str):
        x = [t for t in re.split(r"[,;|]", x.strip("[]")) if t.strip(" '\"")]
    return {_norm(str(t).strip(" '\"")) for t in (x or []) if str(t).strip(" '\"")}


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z0-9.+#]{2,}", (s or "").lower()) if w not in STOP}


def decide(job: dict, persona: dict, portfolio_skills: set[str]) -> tuple[str, str]:
    if job.get("label_scam"):
        return "skip", "scam label"
    js = _skills(job.get("required_skills"))
    shared = js & portfolio_skills
    overlap = len(shared - GENERIC) + (1 if shared & GENERIC else 0)  # all generic tags together count once
    same = job.get("category") == persona["category"]
    b = job.get("budget") or {}
    hi = b.get("max")
    if hi:
        if b.get("type") == "fixed" and hi < 0.5 * persona["floor_usd"]:
            return "skip", f"fixed budget {hi} < half of floor {persona['floor_usd']}"
        if b.get("type") == "hourly" and hi < 0.6 * persona["hourly_rate_usd"]:
            return "skip", f"hourly max {hi} < 60% of rate {persona['hourly_rate_usd']}"
    if same and overlap >= 2:
        return "bid", f"same category, {overlap} skills overlap"
    if (same and overlap == 1) or (not same and overlap >= 2):
        return "watch", f"partial fit (same_category={same}, overlap={overlap})"
    return "skip", f"no fit (same_category={same}, overlap={overlap})"


def relevant(job: dict, items: list[dict]) -> list[str]:
    if job.get("label_scam"):
        return []
    js, jw = _skills(job.get("required_skills")), _words(job.get("title", ""))
    out = []
    for it in items:
        if _skills(it.get("skills")) & js or (_words(it.get("title", "")) & jw):
            out.append(it["evidence_id"])
    return out


def main():
    for d in sorted((ROOT / "evals" / "datasets").glob("dev_*")):
        pid = d.name[4:]
        persona = json.loads((ROOT / "data/personas" / pid / "persona.json").read_text(encoding="utf-8"))
        items = json.loads((ROOT / "data/personas" / pid / "portfolio.json").read_text(encoding="utf-8"))
        port = set().union(*(_skills(i.get("skills")) for i in items)) | _skills(persona.get("skills"))
        port |= {u for u, specific in IMPLIES.items() if specific & port}
        jobs = {j["job_id"]: j for j in json.loads((d / "jobs.json").read_text(encoding="utf-8"))}
        gold = json.loads((d / "gold.json").read_text(encoding="utf-8"))
        counts: dict[str, int] = {}
        for jid, g in gold.items():
            if g.get("action_source") == "human":
                continue  # never overwrite a human label
            base = jobs.get(jid.removesuffix("-inj")) or jobs[jid]
            action, why = decide(base, persona, port)
            g.update({"action": action, "action_source": RUBRIC, "action_reason": why,
                      "relevant": relevant(jobs[jid], items), "relevant_source": RUBRIC})
            counts[action] = counts.get(action, 0) + 1
        (d / "gold.json").write_text(json.dumps(gold, indent=1), encoding="utf-8")
        print(f"{pid}: {counts}  (avg relevant/job: "
              f"{sum(len(g.get('relevant') or []) for g in gold.values()) / max(1, len(gold)):.1f})")


if __name__ == "__main__":
    main()
