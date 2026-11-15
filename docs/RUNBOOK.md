# Runbook

## Run locally
```bash
pip install -e ".[dev]"           # add ".[models]" for sentence-transformers + pypdf
make test                         # unit + MCP + contract + graph integration
make demo                         # one job inbox -> approval -> submit, scam, injection, client reply
MODEL_PROFILE=open OPEN_MODEL_BASE_URL=http://localhost:11434/v1 make demo   # with Ollama models
```
Full stack locally (three terminals):
```bash
uvicorn apps.api.main:app --reload --port 8000             # API (+ in-process MCP servers); docs at /docs
cd apps/web && npm install && npm run dev                   # web on :3000
INTERNAL_TOKEN=... python -m worker.main --loop             # scheduled scouting + outage recovery
```
Or everything in containers: `cp .env.example .env` (fill it), then
`docker compose -f infra/docker-compose.yml up --build` (add `--profile ollama` for local models).

MCP servers standalone: `python -m mcp_servers.portfolio.server` (stdio) or
`MCP_TRANSPORT=http MCP_TOKENS=<token>:<user> python -m mcp_servers.marketplace.server`.

Marketplace: `GIGSIM_BASE_URL=local://` (default once `make data` has run) serves the Kaggle-built
job pool through LocalSim with simulated client replies; `fixture://` is the tiny test set; an
http(s) URL is a real GigSim if one is ever provided.

## Data build
```bash
bash scripts/download_datasets.sh      # needs ~/.kaggle/kaggle.json, or unzip manually into data/raw/<key>/
make data-inspect                      # check every needed field is mapped (edit datapipe/sources.yaml if MISSING)
make data                              # data/market, data/personas, evals/datasets/dev_*
make label-pool                        # relevance sheets (after choosing embedder/reranker)
# fill label_decisions.csv and label_relevance.csv, then:
make labels
```

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

## Deploy (Render blueprint in infra/render.yaml)
1. Push the repo to GitHub. In Render: New -> Blueprint -> select the repo, path `infra/render.yaml`.
2. Fill the `sync: false` values: model provider URL + key, `GIGSIM_BASE_URL`, `WEB_ORIGINS`,
   `API_URL` (worker), `NEXT_PUBLIC_API_URL` (web, needs a rebuild after changing).
3. Open `https://<api>/health`, then register the reviewer account in the web app, run
   onboarding with a persona, and analyse a few jobs so the reviewer sees real state.
4. Check the degraded banner by pointing `GIGSIM_BASE_URL` at a dead URL for a minute.
Any host that runs Docker works the same way (Railway, Fly.io, a VM with compose).

## Secrets
`.env` is never committed (CI fails if it is). Production refuses to start with a weak
`APP_SECRET_KEY`. Upwork OAuth tokens are encrypted at rest (`TOKEN_ENC_KEY`, Fernet).
The reviewer login goes in a private Classroom comment, never in the repo.
