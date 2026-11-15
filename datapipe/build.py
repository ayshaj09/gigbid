"""Build GigBid's data from the approved Kaggle datasets + clearly marked synthetic data.

    python -m datapipe.build [--max-rows-per-file 60000] [--pool 3000] [--dev-size 200]

Outputs (all regenerable; raw data stays in data/raw, git-ignored):
  data/market/jobs.json            job pool served by the local marketplace simulator
  data/market/clients.json         SYNTHETIC client histories (spend calibrated on real contracts)
  data/market/threads.json         SYNTHETIC client conversations
  data/market/market_stats.json    budget / hourly-rate percentiles per category (REAL data)
  data/market/provenance.json      row counts, sources, what is real vs synthetic
  data/personas/<p>/persona.json, portfolio.json        SYNTHETIC personas (rates calibrated on real data)
  evals/datasets/dev_<p>/{jobs.json, gold.json, meta.json, label_decisions.csv}

Field-level provenance: every job has `source` (Kaggle dataset key or `synthetic/...`) and
`synthetic_fields` listing any field we generated (e.g. description for title-only datasets).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import statistics
import time

import pandas as pd

from datapipe.load import ROOT, SOURCES, load_source
from datapipe.synthetic import PERSONAS, _rng, client_history, persona_docs, plant_injection, thread_for

SKILLS = {  # canonical skill -> regex over title/description/skills (lowercased)
    "Python": r"\bpython\b", "Machine Learning": r"machine learning|\bml\b", "LLM": r"\bllm|gpt|openai|chatgpt|claude|gemini",
    "RAG": r"\brag\b|retrieval[- ]augmented|vector (?:db|database)", "LangChain": r"langchain|langgraph", "NLP": r"\bnlp\b|natural language",
    "Computer Vision": r"computer vision|opencv|yolo|image recognition", "Deep Learning": r"deep learning|pytorch|tensorflow|keras",
    "Data Science": r"data scien", "scikit-learn": r"scikit|sklearn", "Forecasting": r"forecast|time series",
    "Chatbot": r"chat ?bot|ai agent|assistant", "AI": r"\bai\b|artificial intelligence",
    "React": r"\breact(?!\s*native)", "React Native": r"react native", "Next.js": r"next\.?js", "Node.js": r"node\.?js|express",
    "TypeScript": r"typescript", "JavaScript": r"javascript|\bjs\b", "Django": r"django", "Flask": r"\bflask\b", "FastAPI": r"fastapi",
    "PHP": r"\bphp\b|laravel", "WordPress": r"wordpress|woocommerce", "Shopify": r"shopify", "Webflow": r"webflow",
    "Full Stack": r"full[- ]?stack", "Frontend": r"front[- ]?end", "Backend": r"back[- ]?end|\bapi\b", "Mobile App": r"mobile app|ios|android|flutter",
    "SQL": r"\bsql\b|postgres|mysql", "Excel": r"excel|spreadsheet|vba", "Power BI": r"power ?bi", "Tableau": r"tableau",
    "Google Sheets": r"google sheets|apps script", "Data Analysis": r"data analy|analytics|dashboard", "Web Scraping": r"scrap|crawler|data extraction",
    "Data Entry": r"data entry", "Statistics": r"statistic|a/b test|regression",
    "Docker": r"docker|kubernetes|k8s", "AWS": r"\baws\b|amazon web services", "DevOps": r"devops|ci/cd|terraform",
    "Graphic Design": r"graphic design|logo|illustrat|photoshop|figma|ui/ux|ux", "Video Editing": r"video edit|premiere|after effects",
    "Content Writing": r"\bwrit|copywrit|blog|article|seo content", "SEO": r"\bseo\b", "Marketing": r"marketing|ads\b|social media",
    "Virtual Assistant": r"virtual assistant|admin support", "Translation": r"translat",
}
CATEGORY_SKILLS = {
    "ai_ml": {"Machine Learning", "LLM", "RAG", "LangChain", "NLP", "Computer Vision", "Deep Learning", "Data Science", "scikit-learn", "Forecasting", "Chatbot", "AI"},
    "web_fullstack": {"React", "React Native", "Next.js", "Node.js", "TypeScript", "JavaScript", "Django", "Flask", "FastAPI", "PHP", "WordPress", "Shopify", "Webflow", "Full Stack", "Frontend", "Backend", "Mobile App"},
    "data_analysis": {"SQL", "Excel", "Power BI", "Tableau", "Google Sheets", "Data Analysis", "Web Scraping", "Data Entry", "Statistics"},
    "devops": {"Docker", "AWS", "DevOps"},
    "design": {"Graphic Design", "Video Editing"},
    "writing": {"Content Writing", "SEO", "Marketing", "Translation", "Virtual Assistant"},
}
_SK = {k: re.compile(v, re.I) for k, v in SKILLS.items()}


def extract_skills(text: str, listed=None) -> list[str]:
    found = [k for k, rx in _SK.items() if rx.search(text or "")]
    if isinstance(listed, str) and listed.strip():
        found += [s.strip(" '\"[]") for s in re.split(r"[,;|]", listed) if s.strip(" '\"[]")]
    return list(dict.fromkeys(found))[:10]


def categorize(skills: list[str]) -> str:
    scores = {c: len(set(skills) & s) for c, s in CATEGORY_SKILLS.items()}
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "other"
    if best == "data_analysis" and "Python" in skills and scores["ai_ml"]:
        return "ai_ml"
    return best


def _num(x) -> float | None:
    try:
        v = float(str(x).replace(",", "").replace("$", "").strip())
        return v if v == v and v > 0 else None
    except (TypeError, ValueError):
        return None


def _hourly(v) -> bool:
    s = str(v).strip().lower()
    return s in ("true", "1", "hourly", "yes") or "hour" in s


def connects_for(budget_type: str, hi: float | None) -> int:
    """SYNTHETIC: Connects cost from budget, mimicking the platform's budget-based tiers."""
    if budget_type == "hourly":
        return 6 if (hi or 0) < 20 else 10 if (hi or 0) < 50 else 16
    hi = hi or 0
    return 2 if hi < 50 else 4 if hi < 100 else 8 if hi < 500 else 12 if hi < 1000 else 16


def synth_description(title: str, skills: list[str], r) -> str:
    """SYNTHETIC description for title-only rows. Restates the title; adds no facts beyond skills."""
    sk = ", ".join(skills[:4]) or "the relevant tools"
    extra = r.choice(["Please share similar work you have done.", "Tell us how you would approach it and how long it would take.",
                      "We need someone who communicates clearly and can start soon.", "Include examples of comparable projects."])
    return f"We are looking for a freelancer for: {title.strip()}. Experience with {sk} is expected. {extra}"


def normalise_jobs(df: pd.DataFrame) -> list[dict]:
    jobs, seen = [], set()
    for r in df.to_dict("records"):  # (itertuples would rename the _source/_file provenance columns)
        title = str(r.get("title") or "").strip()
        if not title or title.lower() == "nan" or len(title) < 8:
            continue
        desc = str(r.get("description") or "").strip()
        desc = "" if desc.lower() == "nan" else re.sub(r"\s+", " ", desc)[:4000]
        key = re.sub(r"\W+", " ", (title + " " + desc[:200]).lower()).strip()
        if key in seen:
            continue  # exact duplicate (reposts across tracker files)
        seen.add(key)
        skills = extract_skills(title + " " + desc, r.get("skills"))
        hourly = _hourly(r.get("is_hourly"))
        lo, hi = (_num(r.get("hourly_low")), _num(r.get("hourly_high"))) if hourly else (None, _num(r.get("budget")))
        if hourly and lo and not hi:
            hi = lo
        if not hourly and hi:
            lo = hi
        rid = hashlib.sha1((str(r.get("link") or "") + title + str(r.get("posted_at"))).encode()).hexdigest()[:10]
        rg = _rng(rid)
        synthetic_fields = ["connects_cost", "client_id"]
        if not desc:
            desc = synth_description(title, skills, rg)
            synthetic_fields.append("description")
        questions = []
        if rg.random() < 0.3:
            questions = [rg.choice(["Describe a similar project you completed.", "How would you approach this?",
                                    "What is your availability?", "Which tools would you use and why?"])]
            synthetic_fields.append("screening_questions")
        btype = "hourly" if hourly else "fixed"
        jobs.append({
            "job_id": f"U-{rid}", "client_id": f"C-{hashlib.sha1(rid.encode()).hexdigest()[:8]}",
            "title": title, "description": desc, "category": categorize(skills), "required_skills": skills,
            "budget": {"min": lo, "max": hi, "type": btype}, "duration_days": None,
            "screening_questions": questions, "connects_cost": connects_for(btype, hi),
            "posted_at": str(r.get("posted_at") or "") or None, "country": None if str(r.get("country")) == "nan" else r.get("country"),
            "source": r.get("_source"), "source_file": r.get("_file"), "link": None if str(r.get("link")) == "nan" else r.get("link"),
            "synthetic_fields": synthetic_fields, "label_scam": False, "label_scam_source": "assumed (platform listing)",
        })
    return jobs


def scam_jobs(fake: pd.DataFrame, n_each: int) -> list[dict]:
    """Real labelled postings (EMSCAD-style). Both fraudulent and legitimate ones are used so scam
    precision can be measured. Clients are drawn from the SAME synthetic distribution for both, so
    detection must come from the text, not from a leaked client signal."""
    if fake.empty or fake["fraudulent"].isna().all():
        return []
    out = []
    fake = fake.assign(fraudulent=pd.to_numeric(fake["fraudulent"], errors="coerce").fillna(0).astype(int))
    for label in (1, 0):
        sub = fake[fake["fraudulent"] == label].sample(frac=1, random_state=7).head(n_each)
        for r in sub.to_dict("records"):
            text = " ".join(str(r.get(k) or "") for k in ("description", "requirements") if str(r.get(k)) != "nan")
            text = re.sub(r"<[^>]+>|\s+", " ", text).strip()[:3000]
            title = str(r.get("title") or "Job")
            if len(text) < 40:
                continue
            rid = hashlib.sha1((title + text[:100]).encode()).hexdigest()[:10]
            skills = extract_skills(title + " " + text)
            rg = _rng(rid)
            hi = rg.choice([150, 300, 600, 1200])
            out.append({
                "job_id": f"F-{rid}", "client_id": f"C-{hashlib.sha1(rid.encode()).hexdigest()[:8]}",
                "title": title, "description": text, "category": categorize(skills), "required_skills": skills,
                "budget": {"min": hi, "max": hi, "type": "fixed"}, "duration_days": None, "screening_questions": [],
                "connects_cost": connects_for("fixed", hi), "posted_at": None, "country": None,
                "source": "fake_job_postings", "source_file": r.get("_file"), "link": None,
                "synthetic_fields": ["budget", "connects_cost", "client_id"],
                "label_scam": bool(label), "label_scam_source": "dataset label `fraudulent`",
            })
    return out


def pct(xs: list[float]) -> dict | None:
    xs = sorted(x for x in xs if x)
    if len(xs) < 5:
        return None
    q = statistics.quantiles(xs, n=4)
    return {"p25": round(q[0], 2), "p50": round(q[1], 2), "p75": round(q[2], 2), "n": len(xs)}


def market_stats(jobs: list[dict], contracts: pd.DataFrame) -> dict:
    stats = {}
    for cat in sorted({j["category"] for j in jobs}):
        js = [j for j in jobs if j["category"] == cat and j["source"] != "fake_job_postings"]
        stats[cat] = {"category": cat,
                      "fixed": pct([j["budget"]["max"] for j in js if j["budget"]["type"] == "fixed"]),
                      "hourly": pct([j["budget"]["max"] for j in js if j["budget"]["type"] == "hourly"]),
                      "source": "real job posts"}
    if not contracts.empty:
        rates = pd.to_numeric(contracts["hourly_rate"], errors="coerce")
        amounts = pd.to_numeric(contracts["amount"], errors="coerce")
        titles = contracts["title"].astype(str)
        cats = [categorize(extract_skills(t)) for t in titles]
        for cat in set(cats):
            mask = [c == cat for c in cats]
            stats.setdefault(cat, {"category": cat, "fixed": None, "hourly": None})
            stats[cat]["contract_hourly_rate"] = pct(list(rates[mask].dropna()))
            stats[cat]["contract_amount"] = pct(list(amounts[mask].dropna()))
    return stats


def persona_rate(pid: str, freelancers: pd.DataFrame) -> float | None:
    if freelancers.empty:
        return None
    rates = pd.to_numeric(freelancers["hourly_rate"], errors="coerce")
    cat = PERSONAS[pid]["category"]
    if freelancers["category"].notna().any():
        words = {"ai_ml": "data|ai|ml|machine", "web_fullstack": "web|develop|software", "data_analysis": "data|analy"}[cat]
        m = freelancers["category"].astype(str).str.contains(words, case=False, regex=True)
        if m.sum() >= 20:
            rates = rates[m]
    med = rates.dropna().median()
    return float(med) if med == med and 5 <= med <= 300 else None


def fair_band(job: dict, stats: dict) -> list[float]:
    b = job["budget"]
    if b.get("min") and b.get("max"):
        return [b["min"], b["max"]] if b["type"] == "hourly" else [round(b["max"] * 0.7), round(b["max"] * 1.1)]
    s = (stats.get(job["category"]) or {}).get(b["type"]) or {}
    return [s.get("p25", 0), s.get("p75", 0)]


def build(max_rows: int, pool: int, dev_size: int):
    t0 = time.time()
    raw_jobs = pd.concat([load_source(k, max_rows) for k in ("upwork_jobs_2024_50k", "upwork_jobs_200k", "upwork_jobs_60k")],
                         ignore_index=True)
    if raw_jobs.empty:
        raise SystemExit("No job files found in data/raw/. Run scripts/download_datasets.sh first.")
    jobs = normalise_jobs(raw_jobs)
    fake = load_source("fake_job_postings")
    contracts = load_source("contracts_1_3m", max_rows * 3)
    freelancers = load_source("freelancer_success")
    scams = scam_jobs(fake, 60)
    stats = market_stats(jobs, contracts)
    amounts = [a for a in pd.to_numeric(contracts.get("amount", pd.Series(dtype=float)), errors="coerce").dropna().tolist() if a > 0][:20000]

    out_m = ROOT / "data" / "market"
    out_m.mkdir(parents=True, exist_ok=True)
    rng = _rng("pool")
    rng.shuffle(jobs)
    dev_ids: set[str] = set()
    dev_sets = {}
    for pid, p in PERSONAS.items():
        rate = persona_rate(pid, freelancers)
        persona, items = persona_docs(pid, rate)
        pdir = ROOT / "data" / "personas" / pid
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "persona.json").write_text(json.dumps(persona, indent=1), encoding="utf-8")
        (pdir / "portfolio.json").write_text(json.dumps(items, indent=1), encoding="utf-8")
        r = _rng("dev", pid)
        same = [j for j in jobs if j["category"] == p["category"] and j["job_id"] not in dev_ids]
        other = [j for j in jobs if j["category"] not in (p["category"], "other") and j["job_id"] not in dev_ids]
        n_same, n_other = int(dev_size * 0.6), int(dev_size * 0.2)
        chosen = same[:n_same] + other[:n_other]
        fakes = [s for s in scams if s["label_scam"]][:dev_size // 20]
        legits = [s for s in scams if not s["label_scam"]][:dev_size // 20]
        inj_src = same[n_same:n_same + dev_size // 20] or same[: dev_size // 20]  # copies with a planted sentence
        inj = [plant_injection(j, i) for i, j in enumerate(inj_src)]
        dev = chosen + fakes + legits + inj
        r.shuffle(dev)
        dev_ids |= {j["job_id"] for j in chosen}
        dev_sets[pid] = (persona, dev)

    pool_jobs = jobs[:pool] + [j for _, d in dev_sets.values() for j in d]
    pool_jobs = list({j["job_id"]: j for j in pool_jobs}.values())
    clients = {j["client_id"]: client_history(j["client_id"], j.get("country"), amounts) for j in pool_jobs}
    threads = [thread_for(j, kind, i) for i, (j, kind) in enumerate(
        zip(pool_jobs[:25], ["interview_request", "question", "negotiation", "scam_signal", "injection"] * 5))]
    (out_m / "jobs.json").write_text(json.dumps(pool_jobs, indent=1, default=str), encoding="utf-8")
    (out_m / "clients.json").write_text(json.dumps(clients, indent=1), encoding="utf-8")
    (out_m / "threads.json").write_text(json.dumps(threads, indent=1), encoding="utf-8")
    (out_m / "market_stats.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")

    for pid, (persona, dev) in dev_sets.items():
        d = ROOT / "evals" / "datasets" / f"dev_{pid}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "jobs.json").write_text(json.dumps(dev, indent=1, default=str), encoding="utf-8")
        gold = {j["job_id"]: {"action": None, "scam": j["label_scam"], "scam_source": j["label_scam_source"],
                              "relevant": None, "fair_band": fair_band(j, stats),
                              "planted_injection": bool(j.get("planted_injection"))} for j in dev}
        gp = d / "gold.json"
        if gp.exists():  # keep human labels already applied
            old = json.loads(gp.read_text(encoding="utf-8"))
            for k, v in old.items():
                if k in gold:
                    gold[k]["action"] = v.get("action")
                    gold[k]["relevant"] = v.get("relevant")
        gp.write_text(json.dumps(gold, indent=1), encoding="utf-8")
        (d / "meta.json").write_text(json.dumps({"persona": pid, "n": len(dev), "built": time.strftime("%Y-%m-%d %H:%M")}, indent=1))
        with open(d / "label_decisions.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["job_id", "action (bid/watch/skip)", "notes", "title", "budget", "category", "description",
                        "persona_headline", "persona_skills"])
            for j in dev:
                b = j["budget"]
                w.writerow([j["job_id"], "", "", j["title"], f"{b['type']} {b.get('min')}-{b.get('max')}", j["category"],
                            j["description"][:700], persona["headline"], ", ".join(persona["skills"][:20])])

    prov = {
        "built": time.strftime("%Y-%m-%d %H:%M"), "seconds": round(time.time() - t0, 1),
        "raw_rows_read": {k: int((raw_jobs["_source"] == k).sum()) for k in raw_jobs["_source"].unique()},
        "jobs_after_dedupe": len(jobs), "pool_jobs": len(pool_jobs),
        "jobs_with_real_description": sum("description" not in j["synthetic_fields"] for j in jobs),
        "jobs_with_synthetic_description": sum("description" in j["synthetic_fields"] for j in jobs),
        "labelled_postings_used": {"fraudulent": sum(s["label_scam"] for s in scams), "legitimate": sum(not s["label_scam"] for s in scams)},
        "contracts_rows_read": len(contracts), "freelancer_rows_read": len(freelancers),
        "categories": {c: sum(j["category"] == c for j in jobs) for c in sorted({j["category"] for j in jobs})},
        "synthetic": ["personas + portfolios", "client histories", "threads", "planted injections",
                      "descriptions/screening questions for title-only rows", "connects costs"],
        "licences": {k: v["licence"] for k, v in SOURCES.items()},
    }
    (out_m / "provenance.json").write_text(json.dumps(prov, indent=1), encoding="utf-8")
    print(json.dumps(prov, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-rows-per-file", type=int, default=60000)
    ap.add_argument("--pool", type=int, default=3000)
    ap.add_argument("--dev-size", type=int, default=200)
    a = ap.parse_args()
    build(a.max_rows_per_file, a.pool, a.dev_size)
