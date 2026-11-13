# Data Card

| Data | Source | Status | Use |
|---|---|---|---|
| `data/fixtures/*` | Written for this repo | Synthetic, hand-labelled | Tests and smoke evals only. 1 persona, 14 evidence items, 8 jobs (2 scams, 1 planted injection, 1 duplicate repost, 1 skill mismatch), 7 client histories, 2 threads. Never reported as results. |
| `data/personas/` | Instructor (GigSim kit) | **Not yet in repo** | Real RAG corpus; `rag/retriever.persona_sources` prefers it automatically. |
| Dev evaluation set | Instructor | **Not yet in repo** | Convert into `evals/datasets/<name>/{jobs.json,gold.json,meta.json}`. |
| Hidden test set | Instructor | Never in repo | Run against the deployed URL only. |
| `data/policy_pack/` | Instructor (starter) | Illustrative starter version | Compliance Guard ground truth. |

Chunk metadata: persona, type, project, skills, date, client_industry, outcome (proposals), source.
Handling: job posts and client messages are untrusted; PII is masked in audit logs; no live-mode
client data is committed.
