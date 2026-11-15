# GigBid: a multi-agent freelancer copilot

GigBid finds freelance jobs, decides whether they are worth bidding on, drafts proposals in which
every claim links to real portfolio evidence, and handles client replies. A human approves every
proposal and message before it leaves the system.

> **Status:** everything that can be built without the instructor's assets is built and tested:
> MCP servers, RAG + claim verification, both LangGraph graphs with durable approvals and memory,
> the FastAPI backend, the Next.js UI, the worker, Docker/Render configs and every experiment
> harness. What remains needs GigSim, the persona corpora, the dev set, real models, a deploy
> account, and your own labels and writing (see "What is left" below).

## Try it
```bash
pip install -e ".[dev,worker,experiments]"
make test        # 82 Python tests: unit, MCP (in-memory client), schema snapshots, graphs, API, harnesses
make demo        # console: scam skipped, injection ignored, inbox -> approval -> submit, client reply
make api         # API on :8000 (OpenAPI at /docs)
make web         # web on :3000 (needs `cd apps/web && npm install` once)
make e2e         # 5 Playwright flows against a real API + built web app
```
Without model settings it runs on the `offline` profile (deterministic rules, no LLM). For
open models: `MODEL_PROFILE=open OPEN_MODEL_BASE_URL=http://localhost:11434/v1 make demo`.

## What is built
| Assignment part | Where | State |
|---|---|---|
| R1 one marketplace port, GigSim + live Upwork adapters | `agent/marketplace_port.py`, `mcp_servers/marketplace/adapters/` | done; Upwork tool names mapped in config (verify with `python -m agent.tools_listing upwork`) |
| A1 Portfolio MCP (tools, resource templates, prompts) | `mcp_servers/portfolio/server.py` | done |
| A2 Marketplace MCP (schemas, annotations, idempotency, dry_run, bearer auth, rate limit, audit) | `mcp_servers/marketplace/server.py` | done |
| A3 Workspace MCP (slots, holds, email drafts) | `mcp_servers/workspace/server.py` | done (local mock) |
| A6 allowlists, timeouts, retries, degraded mode | `agent/mcp_client.py`, `agent/runner.py` | done |
| A7 in-memory MCP tests + schema snapshots | `mcp_servers/*/tests`, `tests/contract` | done (Inspector screenshots: TODO) |
| B1 ingestion (JSON, Markdown, PDF, code, GitHub MCP) | `rag/ingest/` | done |
| B2 variants V0, V1, V2, V3, V4, V8 | `rag/variants/`, `rag/pipeline.py` | done |
| B3 claim verification | `rag/verify.py`, `agent/nodes/verifier.py` | done |
| B4 eval runners (retrieval, decisions, ablation) | `evals/runners/` | done; LLM judge + calibration, GigSim reply rate: TODO |
| C1-C7 bid + conversation graphs, Send fan-out, Critic loop <= 2, interrupts, budgets, Postgres/SQLite checkpointer, style + outcome memory, dead letter | `agent/` | done |
| D web UI: onboarding, inbox, pipeline, job detail, proposal studio, approvals, messages, run viewer, analytics, settings + memory; generated TS client; 5 Playwright flows | `apps/web/` | done |
| E1 worker (scheduled scouting, outage recovery) | `worker/main.py` | done |
| E2 CI: lint, tests, schema snapshots, gigsim hash, secrets, eval gate, web typecheck + e2e | `.github/workflows/` | done |
| E3 tracing (Langfuse/LangSmith, same trace id as audit log) | `agent/tracing.py` | done (needs your keys) |
| E4 Docker compose + Render blueprint | `infra/` | written; not run here (no Docker in my sandbox) |
| R&D A (tool granularity), C (architectures), judge calibration, GigSim outcomes, X2 A/B, failure taxonomy | `evals/runners/` | harnesses done; need real models + data to produce results |
| Portfolio MCP published (`uvx ... gigbid-portfolio-mcp`) | `mcp_servers/portfolio/README.md` | packaged; publishing is your GitHub push |

## Results
Fill from `evals/results/*.json` after running on the real dev set:
`DATASET=<name> make eval`. The fixture runs print warnings and must not be reported.

| Variant | Evidence Recall@5 | nDCG@10 | Unsupported claims / proposal | Judge score | GigSim reply rate | p95 latency (s) | Cost / proposal (USD) |
|---|---|---|---|---|---|---|---|
| V0 | | | | | | | |
| Your best | | | | | | | |

## Data
Real job-market data from six instructor-approved Kaggle datasets plus clearly marked synthetic
personas, clients and conversations; GigSim is replaced by a local simulator over that data.
`bash scripts/download_datasets.sh && make data` builds it; see [Data card](docs/DATA_CARD.md).

## What is left (needs you)
downloading the Kaggle data and `make data`; labelling decisions and evidence relevance; real model and embedding settings; running the
experiments; 30 human labels for the judge; filling the failure taxonomy; the change request;
deployment and the reviewer account; MCP Inspector screenshots; the report, write-up and demo
video. `docs/REPORT_TEMPLATE.md`, `docs/EXTENSION.md` and `docs/WRITEUP_OUTLINE.md` give the structure.

## Docs
[Architecture](docs/ARCHITECTURE.md) · [Tools](docs/TOOLS.md) · [Runbook](docs/RUNBOOK.md) ·
[Data card](docs/DATA_CARD.md) · [AI usage](docs/AI_USAGE.md) · [Extension](docs/EXTENSION.md) ·
[Report template](docs/REPORT_TEMPLATE.md) · [Portfolio MCP](mcp_servers/portfolio/README.md)

## Safety rules the code enforces
Untrusted job posts and messages are fenced and never obeyed (`agent/guardrails.py`); scam flags
are rule-authoritative; Compliance removes contact details, guarantees, invented claims and
injected text; nothing is sent or Connects spent without an `interrupt()` approval; live mode
only creates drafts the user confirms on Upwork; PII is masked in audit logs.
