# MCP Tool Inventory

Generated from `tests/contract/snapshots/` by `python dev/tools_table.py`. A schema change fails CI until the snapshot is regenerated on purpose (`UPDATE_SNAPSHOTS=1 pytest tests/contract`).

| Tool | Server | Read/write | Annotations | Auth / safety |
|---|---|---|---|---|
| `get_case_study` | portfolio | read | idempotent, readOnly | stdio local / bearer over HTTP |
| `list_skills` | portfolio | read | idempotent, readOnly | stdio local / bearer over HTTP |
| `match_requirements` | portfolio | read | idempotent, readOnly | stdio local / bearer over HTTP |
| `search_evidence` | portfolio | read | idempotent, readOnly | stdio local / bearer over HTTP |
| `create_proposal_draft` | marketplace | write | idempotent, openWorld | bearer token -> user (HTTP); stdio local; idempotency_key, dry_run |
| `get_client_history` | marketplace | read | idempotent, openWorld, readOnly | bearer token -> user (HTTP); stdio local |
| `get_connects_balance` | marketplace | read | idempotent, openWorld, readOnly | bearer token -> user (HTTP); stdio local |
| `get_job` | marketplace | read | idempotent, openWorld, readOnly | bearer token -> user (HTTP); stdio local |
| `get_market_stats` | marketplace | read | idempotent, openWorld, readOnly | bearer token -> user (HTTP); stdio local |
| `get_proposal` | marketplace | read | idempotent, openWorld, readOnly | bearer token -> user (HTTP); stdio local |
| `list_messages` | marketplace | read | idempotent, openWorld, readOnly | bearer token -> user (HTTP); stdio local |
| `search_jobs` | marketplace | read | idempotent, openWorld, readOnly | bearer token -> user (HTTP); stdio local |
| `send_message` | marketplace | write | destructive, idempotent, openWorld | bearer token -> user (HTTP); stdio local; idempotency_key, dry_run |
| `submit_proposal` | marketplace | write | destructive, idempotent, openWorld | bearer token -> user (HTTP); stdio local; idempotency_key, dry_run |
| `create_email_draft` | workspace | write |  | stdio local / bearer over HTTP |
| `create_interview_hold` | workspace | write |  | stdio local / bearer over HTTP |
| `free_slots` | workspace | read | idempotent, readOnly | stdio local / bearer over HTTP |

Every marketplace write takes an `idempotency_key` (a repeat returns the first result, stored in
SQLite, so it survives restarts) and `dry_run` (returns the exact payload and Connects cost,
shown on the approval screen). Every marketplace call goes through a per-user token-bucket rate
limiter set below GigSim's limit and writes one line to the append-only audit log
(`data/processed/audit/marketplace.jsonl`: user, tool, masked args, masked result, trace id).

## Per-agent allowlists (A6)
Configured in `agent/config.yaml -> mcp.allowlists`, enforced by `ToolBelt.for_agent()`; a call
outside the list raises `ToolNotAllowed`. Only `submit` and `liaison_send` can reach write tools
with `dry_run=false`, and both run only after an approval interrupt.

## Third-party servers (A5)
| Server | Used for | Trust rationale |
|---|---|---|
| Upwork official MCP (`https://mcp.upwork.com/mcp`) | live mode behind `MarketplacePort` | Operated by the platform itself, OAuth 2.1 scoped to the user, writes are drafts the user confirms on Upwork. |
| GitHub official MCP (`github/github-mcp-server`) | repo ingestion (`rag/ingest/github.py`) | Maintained by GitHub, read-only token scope (`repo:read`/public), we only call `get_file_contents`. |
