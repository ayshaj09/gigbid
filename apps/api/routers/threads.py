from fastapi import APIRouter, Depends, Request

from apps.api.schemas import RunOut
from apps.api.security import current_user

router = APIRouter(prefix="/threads", tags=["messages"])


@router.get("")
def threads(request: Request, user=Depends(current_user)):
    return request.app.state.svc.db.all("SELECT * FROM threads WHERE user_id=? ORDER BY updated DESC", (user["id"],))


@router.post("/{thread_id}/process", response_model=RunOut)
async def process(thread_id: str, request: Request, job_id: str | None = None, user=Depends(current_user)):
    """Read new client messages and draft a reply (stops at approval)."""
    svc = request.app.state.svc
    runner = svc.runner(user)
    run = svc.launch(user, "thread", thread_id, lambda cb: runner.start_conversation(thread_id, job_id, cb))
    return RunOut(run_id=run.run_id, kind="thread", target_id=thread_id, events_url=f"/runs/{run.run_id}/events")


@router.get("/{thread_id}")
async def thread(thread_id: str, request: Request, user=Depends(current_user)):
    runner = request.app.state.svc.runner(user)
    snap = await runner.conv.aget_state({"configurable": {"thread_id": runner.conv_thread(thread_id)}})
    msgs = snap.values.get("messages")
    if msgs is None:
        msgs = await runner._ctx("api").marketplace("client_liaison").list_messages(thread_id)
    intr = snap.tasks[0].interrupts[0].value if snap.tasks and snap.tasks[0].interrupts else None
    return {"thread_id": thread_id, "messages": msgs, "intent": snap.values.get("intent"),
            "status": "awaiting_approval" if intr else snap.values.get("status"), "pending_approval": intr,
            "sent": snap.values.get("sent")}
