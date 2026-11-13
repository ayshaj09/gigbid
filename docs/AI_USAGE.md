# AI Usage Disclosure

> Draft. Review every file listed, then rewrite this in your own words with your own examples.

| Tool | Files / tasks |
|---|---|
| Claude (Anthropic), in Claude.ai | Initial implementation of `agent/`, `rag/`, `mcp_servers/`, `evals/runners/`, `dev/`, fixtures, tests and docs, 13 Nov 2026 |

Things it got wrong that tests caught:
1. Claim verification labelled the writer's own price sentence ("My proposed price is $1425...")
   as an unsupported claim (first person + a number not in evidence) and deleted it from every
   proposal. Fixed by treating commercial terms as offers, not experience claims (`rag/verify.py`, `OFFER`).
2. Interview slots formatted as `2026-11-16 10:00` were masked as phone numbers by the Compliance
   Guard, so the client reply offered ":00; :00". Fixed by formatting slots without digit runs;
   a test now asserts the slot time survives.
