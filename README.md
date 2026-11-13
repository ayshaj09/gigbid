# GigBid: a multi-agent freelancer copilot

GigBid finds freelance jobs, decides whether they are worth bidding on, drafts proposals in which
every claim links to real portfolio evidence, and handles client replies. A human approves every
proposal and message before it leaves the system.

> **Status:** core agent system done (MCP tool layer, RAG + claim verification, both LangGraph
> graphs with approvals, durability and memory). Web UI, API routers, worker, tracing and
> deployment are not built yet. Evaluation numbers below are smoke tests on hand-made fixtures
> until the instructor's GigSim, persona corpora and dev set are added.

## Try it
```bash
pip install -e ".[dev]"
make test     # 67 tests: unit, MCP servers (in-memory client), schema snapshots, graph integration
make demo     # scam skipped, injection ignored, one job inbox -> approval -> submit, one client reply
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
| D web UI, E worker/tracing/deploy, R&D questions A and C, extension | | TODO |

## Results
Fill from `evals/results/*.json` after running on the real dev set:
`DATASET=<name> make eval`. The fixture runs print warnings and must not be reported.

| Variant | Evidence Recall@5 | nDCG@10 | Unsupported claims / proposal | Judge score | GigSim reply rate | p95 latency (s) | Cost / proposal (USD) |
|---|---|---|---|---|---|---|---|
| V0 | | | | | | | |
| Your best | | | | | | | |

## Docs
[Architecture](docs/ARCHITECTURE.md) · [Tools](docs/TOOLS.md) · [Runbook](docs/RUNBOOK.md) ·
[Data card](docs/DATA_CARD.md) · [AI usage](docs/AI_USAGE.md)

## Safety rules the code enforces
Untrusted job posts and messages are fenced and never obeyed (`agent/guardrails.py`); scam flags
are rule-authoritative; Compliance removes contact details, guarantees, invented claims and
injected text; nothing is sent or Connects spent without an `interrupt()` approval; live mode
only creates drafts the user confirms on Upwork; PII is masked in audit logs.
