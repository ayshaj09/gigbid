"""Live progress: Server-Sent Events of node-by-node updates from LangGraph's stream."""
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from apps.api.security import current_user

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("/{run_id}")
def run_info(run_id: str, request: Request, user=Depends(current_user)):
    row = request.app.state.svc.db.one("SELECT * FROM runs WHERE run_id=? AND user_id=?", (run_id, user["id"]))
    if not row:
        raise HTTPException(404, "no such run")
    row["events"] = json.loads(row["events"] or "[]")
    live = request.app.state.svc.runs.get(run_id)
    if live:
        row["events"], row["status"] = live.events, (live.result.status if live.result else "running")
    return row


@router.get("/{run_id}/events")
async def events(run_id: str, request: Request, user=Depends(current_user)):
    run = request.app.state.svc.runs.get(run_id)
    if run is None or run.user_id != user["id"]:
        raise HTTPException(404, "no such live run")

    async def gen():
        sent = 0
        while True:
            async with run.cond:
                if sent >= len(run.events) and not run.done:
                    try:
                        await asyncio.wait_for(run.cond.wait(), timeout=15)
                    except asyncio.TimeoutError:
                        yield {"event": "ping", "data": "{}"}
                        continue
                batch = run.events[sent:]
            for ev in batch:
                sent += 1
                yield {"event": "node", "data": json.dumps(ev)}
            if run.done and sent >= len(run.events):
                return

    return EventSourceResponse(gen())
