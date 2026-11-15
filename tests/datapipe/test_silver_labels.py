"""Silver rubric: deterministic, scam -> skip, budget floor respected, never overwrites human labels."""
import json

import datapipe.silver_labels as S

PERSONA = {"category": "ai_ml", "floor_usd": 300, "hourly_rate_usd": 50}
PORT = {"python", "pytorch", "llm", "rag", "machine learning", "deep learning", "ai", "chatbot"}


def job(**kw):
    base = {"job_id": "J1", "title": "RAG chatbot", "category": "ai_ml", "required_skills": ["LLM", "RAG", "Python"],
            "budget": {"type": "fixed", "min": 1000, "max": 1000}, "label_scam": False}
    return {**base, **kw}


def test_rubric_decisions():
    assert S.decide(job(), PERSONA, PORT)[0] == "bid"
    assert S.decide(job(label_scam=True), PERSONA, PORT)[0] == "skip"
    assert S.decide(job(budget={"type": "fixed", "min": 50, "max": 50}), PERSONA, PORT)[0] == "skip"
    assert S.decide(job(budget={"type": "hourly", "min": 5, "max": 10}), PERSONA, PORT)[0] == "skip"
    assert S.decide(job(required_skills=["LLM"]), PERSONA, PORT)[0] == "watch"
    assert S.decide(job(category="design", required_skills=["Logo"]), PERSONA, PORT)[0] == "skip"


def test_aliases_and_relevance():
    assert S._skills("['Artificial Intelligence', 'ReactJS']") == {"ai", "react"}
    items = [{"evidence_id": "e1", "title": "Invoice extraction", "skills": ["LLM", "OCR"]},
             {"evidence_id": "e2", "title": "Logo pack", "skills": ["Illustrator"]}]
    assert S.relevant(job(), items) == ["e1"]
    assert S.relevant(job(label_scam=True), items) == []


def test_never_overwrites_human(tmp_path, monkeypatch):
    d = tmp_path / "evals/datasets/dev_p"
    d.mkdir(parents=True)
    pdir = tmp_path / "data/personas/p"
    pdir.mkdir(parents=True)
    (pdir / "persona.json").write_text(json.dumps({**PERSONA, "skills": ["Python"]}), encoding="utf-8")
    (pdir / "portfolio.json").write_text(json.dumps([{"evidence_id": "e1", "title": "x", "skills": ["LLM", "RAG"]}]), encoding="utf-8")
    (d / "jobs.json").write_text(json.dumps([job(), job(job_id="J2")]), encoding="utf-8")
    (d / "gold.json").write_text(json.dumps({"J1": {"action": "skip", "action_source": "human"}, "J2": {"action": None}}),
                                 encoding="utf-8")
    monkeypatch.setattr(S, "ROOT", tmp_path)
    S.main()
    gold = json.loads((d / "gold.json").read_text(encoding="utf-8"))
    assert gold["J1"] == {"action": "skip", "action_source": "human"}
    assert gold["J2"]["action"] == "bid" and gold["J2"]["action_source"] == S.RUBRIC
