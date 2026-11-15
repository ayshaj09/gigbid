# AI Usage Disclosure

> Draft. Review every file listed, then rewrite this in your own words with your own examples.

| Tool | Files / tasks |
|---|---|
| Claude (Anthropic), in Claude.ai | Initial implementation of `agent/`, `rag/`, `mcp_servers/`, `evals/runners/`, `dev/`, fixtures, tests and docs, 13 Nov 2026 |
| Claude (Anthropic), in Claude.ai | `apps/api/`, `apps/web/`, `worker/`, `infra/`, experiment harnesses in `evals/`, report templates, 14 Nov 2026 |
| Claude Code (Anthropic), local CLI | Kaggle download and schema mapping (`datapipe/`), silver-label rubric, risk/fit fixes driven by the dev-set evals, open-model retrieval config, CI smoke gate, results/taxonomy scripts, data card, 15 Nov 2026. Commits authored by me, reviewed before committing |

Things it got wrong that tests or evals caught:
1. Claim verification labelled the writer's own price sentence ("My proposed price is $1425...")
   as an unsupported claim (first person + a number not in evidence) and deleted it from every
   proposal. Fixed by treating commercial terms as offers, not experience claims (`rag/verify.py`, `OFFER`).
2. Interview slots formatted as `2026-11-16 10:00` were masked as phone numbers by the Compliance
   Guard, so the client reply offered ":00; :00". Fixed by formatting slots without digit runs;
   a test now asserts the slot time survives.
3. The proposal studio kept the user's old edit box open after Compliance changed an edit, so the
   user could re-send text that no longer matched what was shown. Caught by the Playwright edit
   flow; fixed by keying the studio on the draft text and hiding it while a run is in progress.
4. Its first scam-pattern fix flagged the *project* as the scam: "build a Telegram bot", "PayPal
   integration" and "users create a password" all fired off-platform or credential rules (23 false
   positives across the three dev sets, `evals/results/iterations/1_*`). Fixed by requiring intent
   toward the freelancer ("contact me on ...", "pay you via ..."); scam precision 0.41-0.64 -> 0.64-1.0
   (`iterations/2_*`).
5. It first calibrated persona rates on the median of `freelancer_success.hourly_rate_usd`, which gave
   every persona $280/h. Inspecting the column showed it is clipped at $280, with the median on the
   cap. Rates now come from real job-post p75 ($49-50/h); see `docs/DATA_CARD.md` section 5.
6. A skill lexicon from the first session matched `excel` inside "excellent" and `ads` inside "leads",
   which put telesales and driver posts in the data-analyst dev set. Found while reading the
   data-analyst failures and fixed in `datapipe/build.py` (dev set v2).

