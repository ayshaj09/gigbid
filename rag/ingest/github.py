"""Repo ingestion through the third-party GitHub MCP server (A5/B1).

GitHub's official MCP server (github/github-mcp-server) exposes `get_file_contents`. We read the
README plus a bounded set of source files, so a repo whose README undersells it still contributes
code-level evidence (what V5-style multi-vector indexing exploits).

`call_tool` is an async (name, args) -> result callable from agent.mcp_client.ToolBelt.
"""
from __future__ import annotations

import base64

MAX_FILES = 12
CODE_HINTS = ("train", "model", "pipeline", "api", "main", "app", "tasks", "etl", "retriev", "index")


async def ingest_repo(call_tool, owner: str, repo: str, persona: str, paths: list[str] | None = None) -> list[dict]:
    docs = []
    readme = await _get(call_tool, owner, repo, "README.md")
    if readme:
        docs.append({"evidence_id": f"repo-{repo}", "persona": persona, "type": "repo_readme",
                     "title": f"{owner}/{repo} README", "text": readme, "project": repo, "skills": [],
                     "source": f"github://{owner}/{repo}/README.md"})
    listing = await call_tool("get_file_contents", {"owner": owner, "repo": repo, "path": "/"})
    entries = listing if isinstance(listing, list) else listing.get("entries", []) if isinstance(listing, dict) else []
    candidates = paths or [e["path"] for e in entries
                           if e.get("type") == "file" and e["path"].endswith((".py", ".ts", ".sql"))
                           and any(h in e["path"].lower() for h in CODE_HINTS)]
    for path in candidates[:MAX_FILES]:
        body = await _get(call_tool, owner, repo, path)
        if body:
            docs.append({"evidence_id": f"repo-{repo}-{path.replace('/', '_')}", "persona": persona, "type": "code",
                         "title": f"{repo}/{path}", "text": body[:6000], "project": repo, "skills": [],
                         "source": f"github://{owner}/{repo}/{path}"})
    return docs


async def _get(call_tool, owner, repo, path) -> str | None:
    try:
        res = await call_tool("get_file_contents", {"owner": owner, "repo": repo, "path": path})
    except Exception:  # noqa: BLE001 - missing files are normal
        return None
    if isinstance(res, dict) and res.get("encoding") == "base64":
        return base64.b64decode(res["content"]).decode("utf-8", errors="ignore")
    if isinstance(res, dict):
        return res.get("content") or res.get("text")
    return str(res) if res else None
