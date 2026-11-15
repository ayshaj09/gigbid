"""Settings, autonomy, and the memory viewer (list / delete promoted memory)."""
from fastapi import APIRouter, Depends, Request

from agent.memory.store import delete_style_rule, style_rules
from apps.api.schemas import SettingsIn
from apps.api.security import current_user

router = APIRouter(tags=["settings"])


@router.get("/settings")
def get_settings(request: Request, user=Depends(current_user)):
    svc = request.app.state.svc
    cfg = svc.user_cfg(user)
    persona = svc.persona(user)
    return {"user": user["settings"], "effective": {
        "thresholds": cfg["thresholds"], "autonomy": cfg["autonomy"], "connects": cfg["connects"],
        "model_profile": cfg["models"]["profile"], "retrieval_variant": cfg["retrieval"]["variant"],
        "marketplace_mode": cfg["marketplace"]["mode"],
        "persona": {k: persona.get(k) for k in ("persona_id", "display_name", "hourly_rate_usd", "floor_usd", "saved_searches")}}}


@router.put("/settings")
def put_settings(body: SettingsIn, request: Request, user=Depends(current_user)):
    svc = request.app.state.svc
    settings = {**user["settings"], **body.model_dump(exclude_none=True)}
    svc.db.save_settings(user["id"], settings)
    svc.invalidate(user["id"])
    return {"ok": True, "settings": settings}


@router.get("/memory")
async def memory(request: Request, user=Depends(current_user)):
    store = request.app.state.svc.store
    outcome = await store.asearch(("users", user["id"], "outcome"), limit=100)
    edits = await store.asearch(("users", user["id"], "edit_log"), limit=1000)
    return {"style_rules": await style_rules(store, user["id"]),
            "outcome_stats": {i.key: i.value for i in outcome},
            "edits_logged": len(edits),
            "promotion_rule": "style: same pattern in >=3 of last 10 edits, never contradicted; outcome: >=5 samples per category"}


@router.delete("/memory/style/{rule:path}")
async def forget(rule: str, request: Request, user=Depends(current_user)):
    await delete_style_rule(request.app.state.svc.store, user["id"], rule)
    return {"deleted": rule}
