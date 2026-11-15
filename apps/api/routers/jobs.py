"""Job inbox, analysis runs, job detail."""
from fastapi import APIRouter, Depends, HTTPException, Request

from agent.nodes.scout import scout_saved_searches
from apps.api.schemas import JobRow, Outcome, RunOut, ScoutIn
from apps.api.security import current_user

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _run_out(run) -> RunOut:
    return RunOut(run_id=run.run_id, kind=run.kind, target_id=run.target, events_url=f"/runs/{run.run_id}/events")


@router.get("", response_model=list[JobRow])
def inbox(request: Request, status: str | None = None, min_fit: float | None = None, q: str | None = None,
          user=Depends(current_user)):
    sql, args = "SELECT * FROM jobs WHERE user_id=?", [user["id"]]
    if status:
        sql += " AND status=?"
        args.append(status)
    if min_fit is not None:
        sql += " AND fit>=?"
        args.append(min_fit)
    if q:
        sql += " AND title LIKE ?"
        args.append(f"%{q}%")
    rows = request.app.state.svc.db.all(sql + " ORDER BY updated DESC LIMIT 200", tuple(args))
    return [JobRow(**{**r, "is_scam": bool(r["is_scam"])}) for r in rows]


@router.post("/scout", response_model=list[RunOut])
async def scout(body: ScoutIn, request: Request, user=Depends(current_user)):
    """Run saved searches now (the worker does this on a schedule), queue analysis for new jobs."""
    svc = request.app.state.svc
    runner = svc.runner(user)
    queries = body.queries or runner.persona.get("saved_searches") or []
    port = runner._ctx("scout").marketplace("scout")
    new = await scout_saved_searches(port, svc.store, user["id"], queries)
    runs = []
    for job in new:
        svc.db.upsert_job(user["id"], job, {}, "queued")
        if body.analyse:
            runs.append(_run_out(svc.launch(user, "job", job["job_id"], lambda cb, j=job: runner.start_job(j, cb))))
    return runs


@router.post("/{job_id}/analyze", response_model=RunOut)
async def analyze(job_id: str, request: Request, user=Depends(current_user)):
    svc = request.app.state.svc
    runner = svc.runner(user)
    return _run_out(svc.launch(user, "job", job_id, lambda cb: runner.start_job(job_id, cb)))


@router.get("/{job_id}")
async def detail(job_id: str, request: Request, user=Depends(current_user)):
    svc = request.app.state.svc
    res = await svc.runner(user).job_state(job_id)
    if not res.state:
        raise HTTPException(404, "job not analysed yet")
    s = res.state
    keys = ("job", "job_spec", "risk_report", "fit_report", "decision", "price_quote", "proposal_draft",
            "verification", "critiques", "compliance_verdict", "submission", "status_reason", "evidence", "errors")
    return {"status": res.status, "pending_approval": res.interrupt, **{k: s.get(k) for k in keys},
            "trace": s.get("trace", [])[-40:], "usage": s.get("usage", {})}


@router.get("/{job_id}/history")
async def history(job_id: str, request: Request, user=Depends(current_user)):
    snaps = await request.app.state.svc.runner(user).history(job_id)
    return [{"checkpoint_id": s.config["configurable"].get("checkpoint_id"), "next": list(s.next),
             "status": s.values.get("status"), "step": s.metadata.get("step")} for s in snaps]


@router.post("/{job_id}/outcome")
async def outcome(job_id: str, body: Outcome, request: Request, user=Depends(current_user)):
    """Record what happened (from GigSim or the user) -> outcome memory promotion."""
    import time

    from agent.memory.store import record_outcome
    from rag.text import sentences

    svc = request.app.state.svc
    res = await svc.runner(user).job_state(job_id)
    letter = (res.state.get("proposal_draft") or {}).get("cover_letter", "")
    cat = (res.state.get("job_spec") or {}).get("category", "other")
    svc.db.exec("INSERT OR REPLACE INTO outcomes VALUES (?,?,?,?)", (user["id"], job_id, body.outcome, time.time()))
    promoted = await record_outcome(svc.store, user["id"], cat, body.outcome,
                                    (sentences(letter) or [None])[0], svc.user_cfg(user))
    return {"ok": True, "promoted_categories": list(promoted)}
