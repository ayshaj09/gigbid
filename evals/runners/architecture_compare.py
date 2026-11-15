"""R&D question C: single ReAct agent vs langgraph-supervisor vs GigBid's graph, same model, same jobs.

    MODEL_PROFILE=open python -m evals.runners.architecture_compare --dataset <name> --limit 50

Per architecture: bid/skip F1, scam recall, injection resistance (canary emitted?), unsupported
claims per proposal (same verifier for all), steps (LLM/tool calls), tokens, latency.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
import time

from agent.config import ROOT
from agent.nodes.compliance import injection_canaries
from agent.testing import harness
from evals.baselines import chat_model, mcp_tools, parse_final, react_agent, supervisor_agent
from evals.datasets import backend_for as _backend
from evals.datasets import load
from rag.metrics import f1
from rag.verify import verify_claims


def _tokens(messages) -> int:
    n = 0
    for m in messages:
        u = getattr(m, "usage_metadata", None) or {}
        n += u.get("input_tokens", 0) + u.get("output_tokens", 0)
    return n


async def run_baseline(agent, job: dict, evidence: list[dict]) -> dict:
    t0 = time.perf_counter()
    out = await agent.ainvoke({"messages": [("user", f"Job id {job['job_id']}. Decide and draft.")]},
                              {"recursion_limit": 60})
    msgs = out["messages"]
    final = parse_final(msgs[-1].content if msgs else "")
    letter = final.get("cover_letter") or ""
    rep, _ = verify_claims(letter, evidence) if letter else (None, "")
    return {"action": final.get("action", "skip"), "scam": bool(final.get("is_scam")), "letter": letter,
            "unsupported": rep.unsupported_before if rep else None, "steps": len(msgs), "tokens": _tokens(msgs),
            "latency_s": time.perf_counter() - t0}


async def main(dataset: str, limit: int | None, archs: list[str]):
    jobs, gold, persona = load(dataset)
    ids = [j for j in gold if j in jobs and (gold[j].get("action") or dataset == "fixtures")][:limit]
    rows = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        async with harness(tmp, cfg_overrides={"models": {"profile": "open"}}, persona=persona, backend=_backend(dataset)) as r:
            model = chat_model(r.cfg)
            tools = await mcp_tools(r.belt)
            agents = {"react": react_agent(model, tools), "supervisor": supervisor_agent(model, tools)}
            corpus = list(r.servers["portfolio"].index.items.values())
            for jid in ids:
                job = jobs[jid]
                canaries = injection_canaries(job["description"])
                for arch in archs:
                    if arch == "graph":
                        t0 = time.perf_counter()
                        res = await r.start_job(job)
                        s = res.state
                        letter = (s.get("proposal_draft") or {}).get("cover_letter", "")
                        row = {"action": "bid" if res.status == "awaiting_approval" else (s.get("decision") or {}).get("action", "skip"),
                               "scam": bool((s.get("risk_report") or {}).get("is_scam")), "letter": letter,
                               "unsupported": verify_claims(letter, corpus)[0].unsupported_before if letter else None,
                               "steps": s.get("steps", 0), "latency_s": time.perf_counter() - t0,
                               "tokens": (s.get("usage") or {}).get("tokens_in", 0) + (s.get("usage") or {}).get("tokens_out", 0)}
                    else:
                        row = await run_baseline(agents[arch], job, corpus)
                    row.update(arch=arch, job_id=jid, gold_action=gold[jid]["action"], gold_scam=gold[jid]["scam"],
                               injection_followed=any(c.lower() in (row["letter"] or "").lower() for c in canaries))
                    rows.append(row)
    summary = {}
    for arch in archs:
        rs = [x for x in rows if x["arch"] == arch]
        rs_l = [x for x in rs if x["gold_action"]]
        tp = sum(x["action"] == "bid" and x["gold_action"] == "bid" for x in rs_l)
        fp = sum(x["action"] == "bid" and x["gold_action"] != "bid" for x in rs_l)
        fn = sum(x["action"] != "bid" and x["gold_action"] == "bid" for x in rs_l)
        scams = [x for x in rs if x["gold_scam"]]
        props = [x for x in rs if x["unsupported"] is not None]
        summary[arch] = {"n": len(rs), "bid_skip_f1": round(f1(tp, fp, fn), 3),
                         "scam_recall": round(sum(x["scam"] for x in scams) / len(scams), 3) if scams else None,
                         "injections_followed": sum(x["injection_followed"] for x in rs),
                         "unsupported_per_proposal": round(sum(x["unsupported"] for x in props) / len(props), 3) if props else None,
                         "mean_steps": round(sum(x["steps"] for x in rs) / len(rs), 1),
                         "mean_tokens": round(sum(x["tokens"] for x in rs) / len(rs), 1),
                         "mean_latency_s": round(sum(x["latency_s"] for x in rs) / len(rs), 2)}
    path = ROOT / "evals" / "results" / f"arch_{dataset}_{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps({"dataset": dataset, "summary": summary, "rows": rows}, indent=1, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    print("wrote", path.relative_to(ROOT))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="fixtures")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--archs", default="react,supervisor,graph")
    a = ap.parse_args()
    asyncio.run(main(a.dataset, a.limit, a.archs.split(",")))
