# GigBid: a multi-agent freelancer copilot

GigBid finds freelance jobs, decides whether they are worth bidding on, drafts proposals in which
every claim links to real portfolio evidence, and handles client replies. A human approves every
proposal and message before it leaves the system.

> **Status (15 Nov 2026):** built, tested (90+ Python tests) and **evaluated on real Kaggle job
> data** (217,527 de-duplicated Upwork posts, 115 labelled scam/legit postings) with open models on a
> laptop CPU. Not yet done: public deployment + reviewer login, human labels for judge calibration,
> demo video, write-up (see "What is left").

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
All numbers below come from `evals/results/` (regenerate: `python -m evals.runners.results_table`
→ [`evals/results/results_table.md`](evals/results/results_table.md)). Dev sets: 190 real jobs per
persona; personas and portfolios are synthetic; **decision and relevance labels are silver
(rubric), not human** ([data card §4](docs/DATA_CARD.md)). Profile: rules-only LLM nodes,
`BAAI/bge-small-en-v1.5` embeddings, `cross-encoder/ms-marco-MiniLM-L-6-v2` reranker, CPU only.

**Retrieval (B5, three personas pooled):**

| Variant | Evidence Recall@5 | nDCG@10 | MRR | Unsupported claims / proposal | p95 latency per job (s) | Cost / proposal |
|---|---|---|---|---|---|---|
| V0 naive dense | 0.453 | 0.684 | 0.746 | - | - | - |
| V1 decomposition | 0.365 | 0.599 | 0.687 | - | - | - |
| V2 hybrid (BM25 + dense, RRF) | 0.418 | 0.652 | 0.718 | - | - | - |
| **V3 hybrid + cross-encoder (shipped)** | **0.467** | **0.698** | **0.782** | 0.00 after verification (0.33 before) | 5.5-7.1 | $0 (local) |
| V4 outcome-aware | 0.397 | 0.623 | 0.672 | - | - | - |
| V8 corrective | 0.412 | 0.603 | 0.683 | - | - | - |

Findings: the cross-encoder is the only component that clearly helps. In the V8 ablation, removing
rerank costs 0.054 Recall@5, while removing the corrective loop *gains* 0.055 (the loop re-queries
away from good evidence). Requirement decomposition *hurts* on all three personas, so the
pre-registered hypothesis ("decomposition + hybrid raises Recall@5 on 4+ requirement jobs") is
refuted on this corpus. V3 beats V0 by only 1.4 Recall@5 points, and its retrieval p95 is 4.6-13.3 s
against 0.2-0.8 s for V0 on CPU (`rag_dev_*.json`). Shipped anyway for precision at small k
(MRR +0.036); V0 is the documented fallback if the latency budget tightens.

**Decisions with the shipped config** (`evals/results/decision_dev_*_2026111*.json`):

| Persona | bid/skip F1 | scam precision / recall | injections followed | price in fair band | unsupported claims before → after |
|---|---|---|---|---|---|
| ai_engineer | 0.63 | 0.70 / 0.70 | 0 / 10 | 0.75 | 0.37 → 0.00 |
| web_fullstack | 0.42 | 0.71 / 0.50 | 0 / 10 | 0.57 | 0.47 → 0.00 |
| data_analyst | 0.26 | 0.88 / 0.70 | 0 / 10 | 0.74 | 0.15 → 0.00 |

From the first run on real data to now, bid/skip F1 went from 0.00 / 0.13 / 0.08 to the values above.
That came from six measured fixes, each one commit; see
[`evals/results/iterations/`](evals/results/iterations/README.md) and the
[failure taxonomy](evals/results/failure_taxonomy.md).

## Data
Six instructor-approved Kaggle datasets (ODC-By / Apache-2.0; one with no stated licence, sampled
only) plus clearly marked synthetic personas, portfolios, client histories and threads. Real fields
include titles, descriptions, budgets, Connects costs and, for 749 clients, real spend/rating/
reviews. Build: `bash scripts/download_datasets.sh && make data && python -m datapipe.silver_labels`.
Selection, preprocessing, attribution, licences and limitations: [data card](docs/DATA_CARD.md).

## What is left
1. **Deploy** (Render blueprint in `infra/render.yaml`, or any host) with a reviewer login, and keep it live.
2. **Human labels**: hand-label ≥30 jobs per persona (`label_decisions.csv`) and 30 proposals for
   judge calibration (`python -m evals.runners.judge export`), then re-run `make eval`. Every
   decision number above is silver until then.
3. Run the LLM profiles on a GPU or hosted open-model provider (`MODEL_PROFILE=open`); the CPU
   profiles `open_small` / `open_mixed` work but are slow on a laptop.
4. MCP Inspector screenshots, demo video, technical write-up, publish the Portfolio MCP server.

## Docs
[Architecture](docs/ARCHITECTURE.md) · [Tools](docs/TOOLS.md) · [Runbook](docs/RUNBOOK.md) ·
[Data card](docs/DATA_CARD.md) · [AI usage](docs/AI_USAGE.md) · [Extension](docs/EXTENSION.md) ·
[Report template](docs/REPORT_TEMPLATE.md) · [Portfolio MCP](mcp_servers/portfolio/README.md)

## Safety rules the code enforces
Untrusted job posts and messages are fenced and never obeyed (`agent/guardrails.py`); scam flags
are rule-authoritative; Compliance removes contact details, guarantees, invented claims and
injected text; nothing is sent or Connects spent without an `interrupt()` approval; live mode
only creates drafts the user confirms on Upwork; PII is masked in audit logs.
