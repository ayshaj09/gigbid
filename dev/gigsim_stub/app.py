"""Local GigSim stand-in served over HTTP (NOT the instructor's GigSim; `gigsim/` stays reserved).

Lets `docker compose up` and the GigSimHttp client run end to end before the real simulator is
dropped in. Paths match `marketplace.gigsim.paths` in config.yaml.

    uvicorn dev.gigsim_stub.app:app --port 8081
"""
from __future__ import annotations

import os

from fastapi import FastAPI, Header, HTTPException, Request

from agent.marketplace_port import MarketplaceError, MarketplaceUnavailable
from mcp_servers.marketplace.adapters.gigsim import FixtureGigSim

sim = FixtureGigSim(fail_rate=float(os.environ.get("GIGSIM_STUB_FAIL_RATE", "0")))
app = FastAPI(title="GigSim stub (dev only)")


def _wrap(exc: Exception):
    if isinstance(exc, MarketplaceUnavailable):
        raise HTTPException(503, str(exc))
    raise HTTPException(404 if "not found" in str(exc) else 400, str(exc))


@app.get("/jobs")
async def jobs(q: str = "", limit: int = 20):
    try:
        return {"jobs": await sim.search_jobs(q, limit)}
    except MarketplaceError as exc:
        _wrap(exc)


@app.get("/jobs/{job_id}")
async def job(job_id: str):
    try:
        return await sim.get_job(job_id)
    except MarketplaceError as exc:
        _wrap(exc)


@app.get("/clients/{client_id}/history")
async def client(client_id: str):
    return await sim.get_client_history(client_id)


@app.get("/connects")
async def connects(user_id: str = "default"):
    return await sim.get_connects_balance(user_id)


@app.post("/proposals")
async def create(request: Request, idempotency_key: str = Header(...)):
    body = await request.json()
    try:
        return await sim.create_proposal_draft(body.pop("user_id", "default"), body, idempotency_key)
    except MarketplaceError as exc:
        _wrap(exc)


@app.post("/proposals/{proposal_id}/submit")
async def submit(proposal_id: str, request: Request, idempotency_key: str = Header(...)):
    body = await request.json()
    try:
        return await sim.submit_proposal(body.get("user_id", "default"), proposal_id, idempotency_key)
    except MarketplaceError as exc:
        _wrap(exc)


@app.get("/threads/{thread_id}/messages")
async def messages(thread_id: str):
    return {"messages": await sim.list_messages(thread_id)}


@app.post("/threads/{thread_id}/messages")
async def send(thread_id: str, request: Request, idempotency_key: str = Header(...)):
    body = await request.json()
    return await sim.send_message(body.get("user_id", "default"), thread_id, body["text"], idempotency_key)
