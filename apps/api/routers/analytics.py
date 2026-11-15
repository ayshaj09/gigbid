"""Analytics: bids, replies, Connects spent, approval stats, edit rate, rejection reasons, cost, latency."""
from fastapi import APIRouter, Depends, Request

from apps.api.security import current_user
from rag.metrics import percentile

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("")
def analytics(request: Request, user=Depends(current_user)):
    db = request.app.state.svc.db
    uid = (user["id"],)
    jobs = db.all("SELECT status, action, connects, category FROM jobs WHERE user_id=?", uid)
    submitted = [j for j in jobs if j["status"] == "submitted"]
    outcomes = db.all("SELECT outcome FROM outcomes WHERE user_id=?", uid)
    replied = sum(o["outcome"] in ("replied", "interview", "won", "hired") for o in outcomes)
    appr = db.all("SELECT kind, action, reason FROM approvals WHERE user_id=?", uid)
    runs = db.all("SELECT kind, started, finished, tokens, usd, status FROM runs WHERE user_id=? AND finished IS NOT NULL", uid)
    lat = [r["finished"] - r["started"] for r in runs if r["kind"] == "job"]
    prop_runs = [r for r in runs if r["kind"] == "job" and r["status"] in ("awaiting_approval", "submitted")]
    by_action = {}
    for j in jobs:
        by_action[j["action"] or j["status"]] = by_action.get(j["action"] or j["status"], 0) + 1
    decided = [a for a in appr if a["kind"] == "proposal"]
    return {
        "jobs_analysed": len(jobs), "by_action": by_action, "bids_submitted": len(submitted),
        "connects_spent": sum(j["connects"] or 0 for j in submitted),
        "outcomes_recorded": len(outcomes), "replies": replied,
        "reply_rate": round(replied / len(submitted), 3) if submitted else None,
        "approvals": {a: sum(x["action"] == a for x in decided) for a in ("approve", "edit", "reject")},
        "edit_rate": round(sum(x["action"] == "edit" for x in decided) / len(decided), 3) if decided else None,
        "rejection_reasons": [x["reason"] for x in decided if x["action"] == "reject" and x["reason"]][-20:],
        "usd_per_proposal": round(sum(r["usd"] or 0 for r in prop_runs) / len(prop_runs), 5) if prop_runs else None,
        "tokens_per_job": round(sum(r["tokens"] or 0 for r in runs if r["kind"] == "job") / max(1, len(lat)), 1),
        "p50_latency_s": round(percentile(lat, 50), 3) if lat else None,
        "p95_latency_s": round(percentile(lat, 95), 3) if lat else None,
    }
