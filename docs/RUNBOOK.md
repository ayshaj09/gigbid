# Runbook

## Run locally
```bash
pip install -e ".[dev]"           # add ".[models]" for sentence-transformers + pypdf
make test                         # unit + MCP + contract + graph integration
make demo                         # one job inbox -> approval -> submit, scam, injection, client reply
MODEL_PROFILE=open OPEN_MODEL_BASE_URL=http://localhost:11434/v1 make demo   # with Ollama models
```
MCP servers standalone: `python -m mcp_servers.portfolio.server` (stdio) or
`MCP_TRANSPORT=http MCP_TOKENS=<token>:<user> python -m mcp_servers.marketplace.server`.

GigSim: until the instructor's simulator is in `gigsim/`, `GIGSIM_BASE_URL=fixture://` uses the
in-memory stand-in; `uvicorn dev.gigsim_stub.app:app --port 8081` serves the same over HTTP.

## Rate limits and scheduling
* GigSim: per-user token bucket at `marketplace.max_requests_per_minute` (20) in the Marketplace
  MCP server, below the simulator's limit; 429s honour `Retry-After`.
* Live Upwork: reads every `upwork_live.poll_interval_minutes` (180). Rationale: new-job value
  decays over hours not minutes, 8 polls/day per saved search is indistinguishable from a person
  checking the feed, and it keeps us far from anything resembling scraping.

## Degraded mode
If the marketplace (or its MCP server) fails after node retries, the run stops at its last
checkpoint and `Runner` marks the thread `waiting_for_marketplace` (`agent/runner.py`).
`Runner.retry_waiting()` resumes those threads from the failed node. Tests:
`test_marketplace_outage_parks_then_recovers`, `test_marketplace_server_killed`.

## Crash and resume
Approvals are LangGraph interrupts on a durable checkpointer. After a crash, `Runner.job_state()`
finds the pending approval and `resume_job()` continues. Submission uses deterministic
idempotency keys, so a replayed `submit` is a no-op (`test_crash_while_awaiting_approval_then_resume`,
`test_lost_response_after_submit_is_not_resubmitted`). Replay any job from any node with
`Runner.history(job_id)` and `graph.ainvoke(None, snapshot.config)`.

## Absorbing a policy change
Add an entry to `policy.extra_rules` in `agent/config.yaml` (types listed in `agent/policy.py`).
If the new rule needs a new type, add it in `agent/policy.py` + the one stage that applies it.
