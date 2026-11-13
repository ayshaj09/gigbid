"""CI rule: every prompt lives in agent/prompts/. Flags long instruction-like string literals in code."""
import ast
from pathlib import Path

from agent.config import ROOT, load_prompt, prompt_version

MARKERS = ("you are", "respond with", "your task", "as an ai")


def test_no_inline_prompts():
    offenders = []
    for path in (ROOT / "agent").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) > 200:
                if any(m in node.value.lower() for m in MARKERS):
                    offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, offenders


def test_every_prompt_is_versioned():
    for p in Path(ROOT / "agent/prompts").glob("*.md"):
        if p.name != "README.md":
            assert prompt_version(p.stem).isdigit(), p.name
            assert load_prompt(p.stem)
