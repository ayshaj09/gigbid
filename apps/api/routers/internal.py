"""Internal endpoints the worker calls on a schedule. Protected by INTERNAL_TOKEN, not user JWTs."""
import hmac
import os

from fastapi import APIRouter, Header, HTTPException, Request

from agent.nodes.scout import scout_saved_searches

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


def _check(token: str | None):
    expected = os.environ.get("INTERNAL_TOKEN", "")
    if not expected or not token or not hmac.compare_digest(expected, token):
        raise HTTPException(403, "forbidden")


@router.post("/scout_all")
async def scout_all(request: Request, x_internal_token: str | None = Header(default=None)):
    """Run every onboarded user's saved searches; queue analysis of new jobs (C6 durable queue = runs table)."""
    _check(x_internal_token)
    svc = request.app.state.svc
    queued = 0
    for row in svc.db.all("SELECT id FROM users WHERE onboarded=1"):
        user = svc.db.user(row["id"])
        runner = svc.runner(user)
        port = runner._ctx("scout").marketplace("scout")
        try:
            new = await scout_saved_searches(port, svc.store, user["id"], runner.persona.get("saved_searches") or [])
        except Exception:  # noqa: BLE001 - one user's failure must not stop the others
            svc.marketplace_down_since = svc.marketplace_down_since or __import__("time").time()
            continue
        for job in new:
            svc.db.upsert_job(user["id"], job, {}, "queued")
            svc.launch(user, "job", job["job_id"], lambda cb, j=job, r=runner: r.start_job(j, cb))
            queued += 1
    return {"queued": queued}


@router.post("/retry_waiting")
async def retry_waiting(request: Request, x_internal_token: str | None = Header(default=None)):
    _check(x_internal_token)
    res = await request.app.state.svc.retry_waiting()
    return {"resumed": len(res)}


@router.post("/dev/marketplace")
async def dev_marketplace(request: Request, down: bool, x_internal_token: str | None = Header(default=None)):
    """Test hook (fixture backend, non-production only): take the stand-in marketplace down or up."""
    _check(x_internal_token)
    svc = request.app.state.svc
    if os.environ.get("APP_ENV") == "production" or not hasattr(svc.backend, "down"):
        raise HTTPException(404, "not available")
    svc.backend.down = down
    return {"down": down}
