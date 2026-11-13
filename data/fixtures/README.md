# Fixtures (synthetic, written for this repo)

Small hand-made data for unit/integration tests and the smoke eval while the instructor's persona
corpora, dev set and GigSim are not in this repo. They are NOT the dev set: do not report numbers
computed on them as results. `gold.json` labels are the author's own.

- `persona_ai_engineer.json`, `portfolio_ai_engineer.json`: one persona, 14 evidence items
  (case studies, README + code chunk of the same project, reviews, past proposals with outcomes).
- `jobs.json`: 8 jobs: good fits, a skill mismatch, two scams, one planted prompt injection (J-102),
  one exact duplicate repost (J-105 of J-100).
- `clients.json`, `threads.json`: client histories and two message threads (one scam signal).
