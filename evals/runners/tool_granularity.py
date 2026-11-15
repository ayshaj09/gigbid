"""R&D question A: how tool granularity and descriptions change tool-call accuracy.

    MODEL_PROFILE=open python -m evals.runners.tool_granularity --tasks evals/datasets/tool_tasks.json

Conditions (same model, same tasks):
  fine          all fine-grained read tools with full descriptions
  coarse        coarse tools only where they exist (match_requirements instead of search_evidence)
  terse_docs    fine-grained tools with one-word descriptions
Metrics per condition: first-call tool accuracy, argument validity (schema-valid and key args
correct), wrong-tool calls, calls per task, tokens. Tasks list the expected tool and key args.
"""
from __future__ import annotations

import argparse
import os
import asyncio
import json
import tempfile
import time

from langchain_core.messages import AIMessage

from agent.config import ROOT
from agent.testing import harness
from evals.baselines import chat_model, mcp_tools

CONDITIONS = {
    "fine": {"exclude": {"match_requirements"}, "terse": False},
    "coarse": {"exclude": {"search_evidence"}, "terse": False},
    "terse_docs": {"exclude": {"match_requirements"}, "terse": True},
}
EQUIV = {"coarse": {"search_evidence": "match_requirements"}}


async def run_task(model, tools, task, suffix: str = "") -> dict:
    bound = model.bind_tools(tools)
    t0 = time.perf_counter()
    msg = await bound.ainvoke([("system", "Answer by calling exactly the right tool. Do not answer from memory." + suffix),
                               ("user", task["prompt"])])
    calls = getattr(msg, "tool_calls", []) or []
    usage = getattr(msg, "usage_metadata", None) or {}
    return {"calls": [{"name": c["name"], "args": c["args"]} for c in calls], "latency_s": time.perf_counter() - t0,
            "tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0)}


def score(task, out, condition) -> dict:
    expected = EQUIV.get(condition, {}).get(task["tool"], task["tool"])
    first = out["calls"][0] if out["calls"] else None
    right_tool = bool(first and first["name"] == expected)
    args_ok = right_tool and all(str(v).lower() in json.dumps(first["args"]).lower() for v in task.get("key_args", {}).values())
    return {"right_tool": right_tool, "args_ok": args_ok, "n_calls": len(out["calls"]),
            "wrong_calls": sum(c["name"] != expected for c in out["calls"])}


async def main(tasks_path: str, conditions: list[str], model=None):
    tasks = json.loads((ROOT / tasks_path).read_text(encoding="utf-8"))
    rows = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        profile = os.environ.get("MODEL_PROFILE", "open")
        async with harness(tmp, cfg_overrides={"models": {"profile": profile}} if model is None else None) as r:
            suffix = r.cfg["models"]["profiles"][r.cfg["models"]["profile"]].get("system_suffix", "")
            model = model or chat_model(r.cfg)
            for cond in conditions:
                spec = CONDITIONS[cond]
                tools = [t for t in await mcp_tools(r.belt) if t.name not in spec["exclude"]]
                if spec["terse"]:
                    for t in tools:
                        t.description = t.name.replace("_", " ")
                for task in tasks:
                    out = await run_task(model, tools, task, suffix)
                    rows.append({"condition": cond, "task_id": task["id"], **out, **score(task, out, cond)})
    summary = {}
    for cond in conditions:
        rs = [x for x in rows if x["condition"] == cond]
        summary[cond] = {"n": len(rs), "tool_accuracy": round(sum(x["right_tool"] for x in rs) / len(rs), 3),
                         "arg_accuracy": round(sum(x["args_ok"] for x in rs) / len(rs), 3),
                         "wrong_calls": sum(x["wrong_calls"] for x in rs),
                         "mean_tokens": round(sum(x["tokens"] for x in rs) / len(rs), 1)}
    path = ROOT / "evals" / "results" / f"toolgran_{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps({"summary": summary, "rows": rows}, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return summary, path


def scripted_model_for(tasks):
    """CI smoke: a fake model that always calls the expected tool (checks plumbing, not models)."""
    from evals.baselines import ScriptedChat

    return ScriptedChat(script=[AIMessage(content="", tool_calls=[{"name": t["tool"], "args": t.get("key_args", {}), "id": f"c{i}"}])
                                for i, t in enumerate(tasks)] * len(CONDITIONS))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="evals/datasets/tool_tasks.json")
    ap.add_argument("--conditions", default="fine,coarse,terse_docs")
    a = ap.parse_args()
    asyncio.run(main(a.tasks, a.conditions.split(",")))
