"""Pending approvals across jobs and conversations; approve / edit / reject resumes the graph."""
import time

from fastapi import APIRouter, Depends, HTTPException, Request

from apps.api.schemas import Decision, RunOut
from apps.api.security import current_user

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("")
async def pending(request: Request, user=Depends(current_user)):
    svc = request.app.state.svc
    runner = svc.runner(user)
    out = []
    for row in svc.db.all("SELECT job_id FROM jobs WHERE user_id=? AND status='awaiting_approval'", (user["id"],)):
        res = await runner.job_state(row["job_id"])
        if res.interrupt:
            out.append({"kind": "proposal", "target_id": row["job_id"], "payload": res.interrupt})
    for row in svc.db.all("SELECT thread_id FROM threads WHERE user_id=? AND status='awaiting_approval'", (user["id"],)):
        snap = await runner.conv.aget_state({"configurable": {"thread_id": runner.conv_thread(row["thread_id"])}})
        if snap.tasks and snap.tasks[0].interrupts:
            out.append({"kind": "message", "target_id": row["thread_id"], "payload": snap.tasks[0].interrupts[0].value})
    return out


def _log(svc, user, kind, target, body: Decision):
    svc.db.exec("INSERT INTO approvals (user_id,kind,target_id,action,reason,edited,ts) VALUES (?,?,?,?,?,?,?)",
                (user["id"], kind, target, body.action, body.reason, int(body.action == "edit"), time.time()))


@router.post("/jobs/{job_id}", response_model=RunOut)
async def decide_job(job_id: str, body: Decision, request: Request, user=Depends(current_user)):
    svc = request.app.state.svc
    runner = svc.runner(user)
    state = await runner.job_state(job_id)
    if state.interrupt is None:
        raise HTTPException(409, f"job {job_id} is not waiting for approval (status {state.status})")
    if body.action == "edit" and not (body.edited_text or "").strip():
        raise HTTPException(422, "edit needs edited_text")
    _log(svc, user, "proposal", job_id, body)
    run = svc.launch(user, "job", job_id, lambda cb: runner.resume_job(job_id, body.model_dump(), cb))
    return RunOut(run_id=run.run_id, kind="job", target_id=job_id, events_url=f"/runs/{run.run_id}/events")


@router.post("/threads/{thread_id}", response_model=RunOut)
async def decide_thread(thread_id: str, body: Decision, request: Request, user=Depends(current_user)):
    svc = request.app.state.svc
    runner = svc.runner(user)
    snap = await runner.conv.aget_state({"configurable": {"thread_id": runner.conv_thread(thread_id)}})
    if not (snap.tasks and snap.tasks[0].interrupts):
        raise HTTPException(409, "thread is not waiting for approval")
    _log(svc, user, "message", thread_id, body)
    run = svc.launch(user, "thread", thread_id, lambda cb: runner.resume_conversation(thread_id, body.model_dump()))
    return RunOut(run_id=run.run_id, kind="thread", target_id=thread_id, events_url=f"/runs/{run.run_id}/events")
