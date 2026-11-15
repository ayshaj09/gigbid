"""B1 ingestion: loaders for CVs (PDF), case studies (Markdown), repo READMEs and code, reviews and
past proposals; every chunk carries persona, type, project, skills, date, client industry and,
for proposals, outcome.

Supported inputs
  * JSON list of evidence items (fixtures / instructor persona export)
  * a directory tree: *.md (case studies, READMEs; optional `key: value` front matter),
    *.pdf (CV; needs `pypdf`), code files (*.py, *.ts, *.js, *.sql, *.ipynb as text),
    proposals/*.json with an `outcome` field, reviews/*.json|md
  * GitHub repos through the GitHub MCP server (see github.py)
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from rag.text import tokens

CODE_EXT = {".py", ".ts", ".tsx", ".js", ".sql", ".go", ".rs", ".java", ".ipynb"}
TYPE_BY_DIR = {"case_studies": "case_study", "reviews": "review", "proposals": "past_proposal",
               "repos": "repo_readme", "cv": "cv"}


def _front_matter(text: str) -> tuple[dict, str]:
    meta: dict = {}
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            for line in text[3:end].strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    v = v.strip()
                    meta[k.strip()] = [s.strip() for s in v.strip("[]").split(",")] if v.startswith("[") else v
            text = text[end + 4 :]
    return meta, text.strip()


def _doc_id(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "-", path.stem)[:40] + "-" + hashlib.md5(str(path).encode()).hexdigest()[:6]


def load_json_items(path: Path, persona: str | None = None) -> list[dict]:
    items = json.loads(Path(path).read_text(encoding="utf-8"))
    for it in items:
        it.setdefault("persona", persona or it.get("freelancer_id"))
        it.setdefault("text", it.get("summary", ""))
        it.setdefault("project", it["evidence_id"])
        it.setdefault("skills", [])
        it.setdefault("source", str(path))
    return items


def load_directory(root: Path, persona: str) -> list[dict]:
    docs = []
    for path in sorted(Path(root).rglob("*")):
        if not path.is_file():
            continue
        dtype = next((t for d, t in TYPE_BY_DIR.items() if d in path.parts), None)
        if path.suffix == ".md":
            meta, body = _front_matter(path.read_text(encoding="utf-8", errors="ignore"))
            dtype = meta.get("type") or dtype or ("repo_readme" if path.name.lower() == "readme.md" else "case_study")
        elif path.suffix == ".pdf":
            body, meta, dtype = _read_pdf(path), {}, dtype or "cv"
        elif path.suffix in CODE_EXT:
            body, meta, dtype = path.read_text(encoding="utf-8", errors="ignore"), {}, "code"
        elif path.suffix == ".json" and dtype in ("past_proposal", "review"):
            raw = json.loads(path.read_text(encoding="utf-8"))
            body, meta = raw.get("text", ""), raw
        else:
            continue
        project = meta.get("project") or (path.parent.name if dtype in ("code", "repo_readme") else path.stem)
        docs.append({
            "evidence_id": meta.get("id") or _doc_id(path),
            "persona": persona, "type": dtype, "title": meta.get("title") or path.stem.replace("_", " "),
            "text": body, "project": project, "skills": meta.get("skills") or [],
            "date": meta.get("date"), "client_industry": meta.get("client_industry"),
            "outcome": meta.get("outcome"), "source": str(path),
        })
    return docs


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("pip install pypdf to ingest PDF CVs") from exc
    return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)


def chunk(doc: dict, max_words: int = 180, overlap_words: int = 30) -> list[dict]:
    """Fixed-size word windows with overlap. Short docs (most evidence items) stay one chunk.
    Each chunk keeps all of the parent's metadata so filters and outcome boosts work per chunk."""
    words = doc["text"].split()
    if len(words) <= max_words:
        spans = [(0, len(words))]
    else:
        step = max_words - overlap_words
        spans = [(i, min(i + max_words, len(words))) for i in range(0, len(words) - overlap_words, step)]
    out = []
    for n, (a, b) in enumerate(spans):
        meta = {k: v for k, v in doc.items() if k != "text"}
        out.append({**meta, "chunk_id": f"{doc['evidence_id']}#c{n}", "text": " ".join(words[a:b]),
                    "_tokens": tokens(doc.get("title", "") + " " + " ".join(words[a:b]) + " " + " ".join(doc.get("skills", [])))})
    return out
