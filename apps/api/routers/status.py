"""System status for the UI banner (degraded mode) and a manual retry."""
import asyncio
import time

from fastapi import APIRouter, Depends, Request

from apps.api.security import current_user

router = APIRouter(tags=["status"])


@router.get("/status")
async def status(request: Request, user=Depends(current_user)):
    svc = request.app.state.svc
    ok, detail = True, ""
    try:
        port = svc.runner(user)._ctx("status").marketplace("pricing")
        await asyncio.wait_for(port.get_connects_balance(), 5)
    except asyncio.TimeoutError:
        # A slow probe while agent runs hold the CPU means "busy", not "down": only a server the
        # tool belt has actually marked down (failed calls after retries) raises the banner.
        down = getattr(svc.belt, "down", set())
        ok, detail = "marketplace" not in down, "marketplace busy (probe timed out)"
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, str(exc)[:200]
    waiting = svc.db.one("SELECT COUNT(*) n FROM jobs WHERE user_id=? AND status='waiting_for_marketplace'", (user["id"],))["n"]
    return {"marketplace_ok": ok, "detail": detail, "queued_while_down": waiting,
            "down_for_s": round(time.time() - svc.marketplace_down_since) if svc.marketplace_down_since else 0,
            "mcp_servers_down": sorted(getattr(svc.belt, "down", set()))}


@router.post("/status/retry")
async def retry(request: Request, user=Depends(current_user)):
    results = await request.app.state.svc.retry_waiting()
    return {"resumed": [{"thread": r.thread_id, "status": r.status} for r in results]}
