"""GigBid API. Run: uvicorn apps.api.main:app --reload --port 8000  (OpenAPI at /docs)."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.routers import analytics, approvals, auth, internal, jobs, onboarding, runs, settings, status, threads
from apps.api.service import Service


@asynccontextmanager
async def lifespan(app: FastAPI):
    svc = Service()
    await svc.start()
    app.state.svc = svc
    try:
        yield
    finally:
        await svc.stop()


app = FastAPI(title="GigBid API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("WEB_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["*"], allow_headers=["*"], allow_credentials=False,
)
for r in (auth, onboarding, jobs, approvals, threads, runs, analytics, settings, status, internal):
    app.include_router(r.router)


@app.get("/health", tags=["status"])
async def health():
    return {"status": "ok", "service": "gigbid-api"}
