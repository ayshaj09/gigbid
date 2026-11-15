"""Onboarding: pick a persona (or upload a portfolio), set rate, floor, Connects budget, saved searches."""
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile

from agent.config import ROOT
from apps.api.schemas import Onboarding
from apps.api.security import current_user

router = APIRouter(tags=["onboarding"])
ALLOWED = {".md", ".txt", ".pdf", ".json", ".py", ".ts", ".sql"}
MAX_BYTES = 5 * 1024 * 1024


@router.get("/personas")
def personas():
    """Personas this deployment serves. One Portfolio MCP server runs per deployment, so only its
    persona (PORTFOLIO_PERSONA) is offered; uploads add to that portfolio."""
    import os

    from rag.retriever import load_persona

    served = os.environ.get("PORTFOLIO_PERSONA", "ai_engineer")
    out = []
    for d in [load_persona(served)]:
        out.append({"persona_id": d["persona_id"], "display_name": d.get("display_name"), "headline": d.get("headline"),
                    "skills": d.get("skills", [])[:12], "hourly_rate_usd": d.get("hourly_rate_usd"),
                    "floor_usd": d.get("floor_usd"), "saved_searches": d.get("saved_searches", [])})
    return out


@router.post("/onboarding")
def onboard(body: Onboarding, request: Request, user=Depends(current_user)):
    svc = request.app.state.svc
    settings = {**user["settings"], **body.model_dump(exclude={"persona_id", "marketplace_mode"}),
                "marketplace_mode": body.marketplace_mode}
    svc.db.save_settings(user["id"], settings, persona_id=body.persona_id, onboarded=True)
    svc.invalidate(user["id"])
    return {"ok": True}


@router.post("/portfolio/upload")
async def upload(file: UploadFile, request: Request, user=Depends(current_user)):
    """Store an uploaded case study / CV / README and add it to the portfolio index (in-process MCP)."""
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", file.filename or "upload")
    if Path(name).suffix.lower() not in ALLOWED:
        raise HTTPException(415, f"allowed types: {', '.join(sorted(ALLOWED))}")
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "file too large (5 MB max)")
    dest = ROOT / "data" / "processed" / "uploads" / user["id"] / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    svc = request.app.state.svc
    added = 0
    servers = getattr(svc, "servers", None)
    if servers:
        from rag.ingest.loaders import load_directory

        docs = [d for d in load_directory(dest.parent, user.get("persona_id") or "upload") if d["source"] == str(dest)]
        added = servers["portfolio"].index.add(docs)
    return {"stored": name, "chunks_indexed": added}
