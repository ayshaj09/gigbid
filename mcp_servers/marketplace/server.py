"""Marketplace MCP server (A2): wraps GigSim with typed, annotated, idempotent, audited tools.

Read tools:  search_jobs, get_job, get_client_history, get_connects_balance, list_messages,
             get_market_stats
Write tools: create_proposal_draft, submit_proposal, send_message
             - every write takes an `idempotency_key`; a retried call returns the first result
             - every write takes `dry_run`; it returns exactly what would be sent and what it costs
Every call: per-user rate limit (below GigSim's), append-only audit log with trace id.

Run:  python -m mcp_servers.marketplace.server             (stdio)
      MCP_TRANSPORT=http MCP_TOKENS=tok:alice python -m mcp_servers.marketplace.server
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from agent.config import load_config
from agent.marketplace_port import MarketplaceError, MarketplaceUnavailable
from mcp_servers.common import DATA_DIR, AuditLog, IdempotencyStore, RateLimiter, run_server
from mcp_servers.marketplace.adapters.gigsim import make_backend

# ---- shared argument types (real constraints, surfaced in the JSON schema) -----------------
UserId = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$",
                              description="GigBid user id (overridden by the bearer token over HTTP)")]
TraceId = Annotated[str | None, Field(default=None, max_length=64, description="Trace id to correlate logs")]
JobId = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]
IdemKey = Annotated[str, Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$",
                               description="Same key => same effect at most once")]

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)


# ---- output schemas --------------------------------------------------------------------------
class Budget(BaseModel):
    min: float | None = None
    max: float | None = None
    type: str = "fixed"


class Job(BaseModel):
    job_id: str
    client_id: str | None = None
    title: str
    description: str
    category: str = "other"
    required_skills: list[str] = []
    budget: Budget = Budget()
    duration_days: int | None = None
    screening_questions: list[str] = []
    connects_cost: int = 0
    posted_at: str | None = None


class JobList(BaseModel):
    jobs: list[Job]


class ClientHistory(BaseModel):
    client_id: str
    payment_verified: bool = False
    total_spent_usd: float = 0
    hires: int = 0
    jobs_posted: int = 0
    average_rating: float | None = None
    country: str | None = None
    industry: str | None = None


class ConnectsBalance(BaseModel):
    user_id: str
    balance: int


class Percentiles(BaseModel):
    p25: float
    p50: float
    p75: float
    n: int


class MarketStats(BaseModel):
    category: str
    fixed: Percentiles | None = None
    hourly: Percentiles | None = None


class Message(BaseModel):
    id: str
    sender: str
    text: str
    at: str | None = None


class MessageList(BaseModel):
    thread_id: str
    messages: list[Message]


class WriteResult(BaseModel):
    dry_run: bool
    idempotent_replay: bool = False
    action: str
    would_send: dict[str, Any] | None = None
    cost_connects: int = 0
    connects_balance_after: int | None = None
    result: dict[str, Any] | None = None


def _user(ctx: Context | None, user_id: str) -> str:
    """Over HTTP, the bearer token decides the user; the argument cannot impersonate anyone."""
    try:
        req = ctx.request_context.request if ctx else None
        if req is not None and "gigbid_user" in req.scope:
            return req.scope["gigbid_user"]
    except (AttributeError, LookupError, ValueError):
        pass
    return user_id


def build_server(backend=None, cfg: dict | None = None, data_dir: Path | None = None) -> FastMCP:
    cfg = cfg or load_config()
    backend = backend or make_backend(cfg)
    data_dir = Path(data_dir or DATA_DIR)
    audit = AuditLog(data_dir / "audit" / "marketplace.jsonl")
    idem = IdempotencyStore(data_dir / "marketplace_idem.sqlite")
    limiter = RateLimiter(cfg["marketplace"]["max_requests_per_minute"])
    mcp = FastMCP("gigbid-marketplace", instructions=(
        "GigBid marketplace tools wrapping GigSim. Writes require an idempotency_key and should be "
        "previewed with dry_run=true before a human approves them."))
    mcp.backend = backend  # exposed for tests
    mcp.audit = audit

    async def guarded(tool: str, user: str, trace_id: str | None, args: dict, fn):
        try:
            await limiter.acquire(user)
        except RuntimeError as exc:
            audit.write(user_id=user, tool=tool, args=args, result=str(exc), trace_id=trace_id, ok=False)
            raise ToolError(str(exc)) from exc
        try:
            result = await fn()
        except MarketplaceUnavailable as exc:
            audit.write(user_id=user, tool=tool, args=args, result=str(exc), trace_id=trace_id, ok=False)
            raise ToolError(f"UNAVAILABLE: {exc}") from exc
        except MarketplaceError as exc:
            audit.write(user_id=user, tool=tool, args=args, result=str(exc), trace_id=trace_id, ok=False)
            raise ToolError(f"ERROR: {exc}") from exc
        dumped = result.model_dump() if isinstance(result, BaseModel) else result
        audit.write(user_id=user, tool=tool, args=args, result=dumped, trace_id=trace_id)
        return result

    # ---------------------------------------------------------------- read tools
    @mcp.tool(annotations=READ, description="Search open jobs by keywords. Returns up to `limit` jobs.")
    async def search_jobs(
        query: Annotated[str, Field(min_length=1, max_length=200)],
        limit: Annotated[int, Field(ge=1, le=50)] = 20,
        user_id: UserId = "default", trace_id: TraceId = None, ctx: Context | None = None,
    ) -> JobList:
        user = _user(ctx, user_id)
        async def run():
            return JobList(jobs=[Job.model_validate(j) for j in await backend.search_jobs(query, limit)])
        return await guarded("search_jobs", user, trace_id, {"query": query, "limit": limit}, run)

    @mcp.tool(annotations=READ, description="Get one job post by id, including budget, screening questions and Connects cost.")
    async def get_job(job_id: JobId, user_id: UserId = "default", trace_id: TraceId = None,
                      ctx: Context | None = None) -> Job:
        user = _user(ctx, user_id)
        async def run():
            return Job.model_validate(await backend.get_job(job_id))
        return await guarded("get_job", user, trace_id, {"job_id": job_id}, run)

    @mcp.tool(annotations=READ, description="Get a client's marketplace history: spend, hires, rating, payment verification.")
    async def get_client_history(client_id: JobId, user_id: UserId = "default", trace_id: TraceId = None,
                                 ctx: Context | None = None) -> ClientHistory:
        user = _user(ctx, user_id)
        async def run():
            return ClientHistory.model_validate(await backend.get_client_history(client_id))
        return await guarded("get_client_history", user, trace_id, {"client_id": client_id}, run)

    @mcp.tool(annotations=READ, description="Get the user's current Connects balance.")
    async def get_connects_balance(user_id: UserId = "default", trace_id: TraceId = None,
                                   ctx: Context | None = None) -> ConnectsBalance:
        user = _user(ctx, user_id)
        async def run():
            return ConnectsBalance.model_validate(await backend.get_connects_balance(user))
        return await guarded("get_connects_balance", user, trace_id, {}, run)

    @mcp.tool(annotations=READ, description="Budget percentiles (p25/p50/p75) for a job category from historical jobs.")
    async def get_market_stats(category: Annotated[str, Field(min_length=1, max_length=40)],
                               user_id: UserId = "default", trace_id: TraceId = None,
                               ctx: Context | None = None) -> MarketStats:
        user = _user(ctx, user_id)
        async def run():
            return MarketStats.model_validate(await backend.get_market_stats(category))
        return await guarded("get_market_stats", user, trace_id, {"category": category}, run)

    @mcp.tool(annotations=READ, description="List messages in a client conversation thread, oldest first.")
    async def list_messages(thread_id: JobId, user_id: UserId = "default", trace_id: TraceId = None,
                            ctx: Context | None = None) -> MessageList:
        user = _user(ctx, user_id)
        async def run():
            msgs = await backend.list_messages(thread_id)
            return MessageList(thread_id=thread_id, messages=[Message.model_validate(m) for m in msgs])
        return await guarded("list_messages", user, trace_id, {"thread_id": thread_id}, run)

    # ---------------------------------------------------------------- write tools
    async def idempotent_write(tool, user, key, trace_id, args, preview, act) -> WriteResult:
        if args.get("dry_run"):
            return await guarded(tool, user, trace_id, args, preview)
        cached = idem.get(user, tool, key)
        if cached is not None:
            replay = WriteResult.model_validate({**cached, "idempotent_replay": True})
            audit.write(user_id=user, tool=tool, args=args, result={"replay": True}, trace_id=trace_id)
            return replay
        result = await guarded(tool, user, trace_id, args, act)
        idem.put(user, tool, key, result.model_dump())
        return result

    @mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True),
        description="Create (not submit) a proposal draft on the marketplace. Use dry_run=true to preview.",
    )
    async def create_proposal_draft(
        job_id: JobId,
        cover_letter: Annotated[str, Field(min_length=40, max_length=5000)],
        bid_amount: Annotated[float, Field(gt=0, le=1_000_000)],
        idempotency_key: IdemKey,
        bid_type: Literal["fixed", "hourly"] = "fixed",
        screening_answers: Annotated[list[Annotated[str, Field(max_length=2000)]], Field(max_length=10)] = [],  # noqa: B006
        dry_run: bool = False,
        user_id: UserId = "default", trace_id: TraceId = None, ctx: Context | None = None,
    ) -> WriteResult:
        user = _user(ctx, user_id)
        payload = {"job_id": job_id, "cover_letter": cover_letter, "bid_amount": bid_amount,
                   "bid_type": bid_type, "screening_answers": screening_answers}
        args = {**payload, "idempotency_key": idempotency_key, "dry_run": dry_run}

        async def preview():
            job = await backend.get_job(job_id)
            bal = (await backend.get_connects_balance(user))["balance"]
            return WriteResult(dry_run=True, action="create_proposal_draft", would_send=payload,
                               cost_connects=job.get("connects_cost", 0),
                               connects_balance_after=bal - job.get("connects_cost", 0))

        async def act():
            res = await backend.create_proposal_draft(user, payload, idempotency_key)
            return WriteResult(dry_run=False, action="create_proposal_draft", result=res,
                               cost_connects=0)

        return await idempotent_write("create_proposal_draft", user, idempotency_key, trace_id, args, preview, act)

    @mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True),
        description="Submit an existing proposal draft. SPENDS CONNECTS. Only after human approval. dry_run previews cost.",
    )
    async def submit_proposal(
        proposal_id: JobId, idempotency_key: IdemKey, dry_run: bool = False,
        user_id: UserId = "default", trace_id: TraceId = None, ctx: Context | None = None,
    ) -> WriteResult:
        user = _user(ctx, user_id)
        args = {"proposal_id": proposal_id, "idempotency_key": idempotency_key, "dry_run": dry_run}

        async def preview():
            prop = getattr(backend, "proposals", {}).get(proposal_id, {})
            bal = (await backend.get_connects_balance(user))["balance"]
            cost = prop.get("connects_cost", 0)
            return WriteResult(dry_run=True, action="submit_proposal", would_send={"proposal_id": proposal_id},
                               cost_connects=cost, connects_balance_after=bal - cost)

        async def act():
            res = await backend.submit_proposal(user, proposal_id, idempotency_key)
            bal = (await backend.get_connects_balance(user))["balance"]
            return WriteResult(dry_run=False, action="submit_proposal", result=res,
                               cost_connects=res.get("connects_cost", 0), connects_balance_after=bal)

        return await idempotent_write("submit_proposal", user, idempotency_key, trace_id, args, preview, act)

    @mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True),
        description="Send a message to a client thread. Only after human approval. dry_run previews it.",
    )
    async def send_message(
        thread_id: JobId, text: Annotated[str, Field(min_length=1, max_length=4000)], idempotency_key: IdemKey,
        dry_run: bool = False, user_id: UserId = "default", trace_id: TraceId = None, ctx: Context | None = None,
    ) -> WriteResult:
        user = _user(ctx, user_id)
        args = {"thread_id": thread_id, "text": text, "idempotency_key": idempotency_key, "dry_run": dry_run}

        async def preview():
            return WriteResult(dry_run=True, action="send_message", would_send={"thread_id": thread_id, "text": text})

        async def act():
            return WriteResult(dry_run=False, action="send_message",
                               result=await backend.send_message(user, thread_id, text, idempotency_key))

        return await idempotent_write("send_message", user, idempotency_key, trace_id, args, preview, act)

    return mcp


if __name__ == "__main__":
    run_server(build_server(), int(os.environ.get("MCP_PORT", 8102)))
