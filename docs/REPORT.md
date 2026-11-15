# GigBid — R&D report (draft)

> Draft built from the committed results. Every number cites a file in `evals/results/` or a
> commit. Sections marked **[TODO: you]** need work only the author can do. Rewrite in your own
> words before exporting to PDF (≤ 10 pages + appendices).

## 1. Problem and constraints
Freelancers lose hours scanning feeds, spend paid Connects on unwinnable jobs, send generic
proposals and meet scams (free work, off-platform payment). GigBid automates discovery, assessment
and drafting. A human makes every decision that costs money or leaves the system.

**Never automated:** submitting a proposal, sending a message, spending Connects. Each goes through
a LangGraph `interrupt()` and explicit approval in the UI (C5). Live mode only creates drafts the
user confirms on Upwork.

**Declared budgets** (`agent/config.yaml: budgets.declared`): p95 ≤ 20 s per job analysed and
≤ 60 s per proposal; ≤ $0.002 per job and ≤ $0.01 per proposal. Measured on the open, local,
CPU-only configuration: p95 5.5–7.1 s per job (`decision_dev_*_2026111*.json`), $0 (local models).

## 2. Architecture
See `docs/ARCHITECTURE.md` and the graphs rendered from code (`make graphs`). Bid graph: Scout →
{Job Analyst ∥ Risk Assessor ∥ Fit Matcher} (`Send`) → decide → Pricing → Writer → claim
verification → Critic (≤ 2 loops) → Compliance → `interrupt()` → submit. Conversation graph:
Client Liaison → intent → draft/slots → `interrupt()`. One marketplace port with GigSim and live
Upwork adapters (R1). Three own MCP servers plus Upwork and GitHub (R2). State, the execution
trace and long-term memory are separate stores. Style and outcome memory are written only through
the promotion rules in `agent/memory/promotion_rules.py`.

**Data** (`docs/DATA_CARD.md`): 293,058 rows from three Upwork job scrapes, de-duplicated to
217,527 jobs. 180k completed contracts supply pricing statistics. 115 labelled real/fake postings
supply scam ground truth. Personas, portfolios, client histories and threads are synthetic and
marked as such. There was no instructor dev set, so decision and relevance labels come from a
documented rubric (`silver_rubric_v2`). They are **silver, not human**, and every eval JSON
records this in `label_sources`.

## 3. R&D question A — tool granularity
**Setup:** 40 tasks with known correct calls (`evals/datasets/tool_tasks.json`); model qwen3:1.7b
(`open_small`, Ollama on CPU, no-think); one call per task; same tasks and model in each condition.
File: `evals/results/toolgran_20261115-174327.json`.

| Condition | Tool-selection accuracy | Argument accuracy | Wrong calls | Mean tokens / task | Mean latency (s) |
|---|---|---|---|---|---|
| fine (all fine-grained tools, full descriptions) | 0.925 | 0.925 | 2 | 1,389 | 46.1 |
| coarse (`match_requirements` instead of `search_evidence`) | 0.800 | 0.800 | 5 | 1,414 | 52.8 |
| terse_docs (fine tools, one-word descriptions) | 0.950 | 0.900 | 1 | 1,281 | 43.2 |

**Findings:**
- Granularity matters more than description length. With the coarse set, the model avoided the
  one multi-purpose tool: 5 of its 8 failures called `list_skills` or nothing instead of
  `match_requirements`.
- Shorter descriptions did not hurt tool choice (0.95 vs 0.925, one task). They cost one argument
  error and saved 108 tokens per task.
- The differences are 1–5 tasks out of 40, so only coarse vs fine is a meaningful gap.

**Decision:** keep fine-grained tools. Keep full descriptions on the write tools and on tools with
non-obvious arguments (the one terse-docs argument error was there). The assignment's third
condition, "best set with rewritten descriptions", was not run; it is the next experiment.

## 4. R&D question B — retrieval, verification, ablation
**Hypothesis** (taken from the assignment brief, *not* separately pre-registered; commit your own
before re-running): requirement decomposition plus hybrid retrieval raises evidence Recall@5 over
V0 on jobs with ≥ 4 requirements.

**Setup:** 190 dev jobs per persona; silver relevance (skill-tag or title overlap); open models
`bge-small-en-v1.5` and `ms-marco-MiniLM-L-6-v2`; CPU.

**Results** (`evals/results/results_table.md`, from `rag_dev_*_20261115-*.json`):

| Variant | Recall@5 | nDCG@10 | MRR |
|---|---|---|---|
| V0 naive | 0.453 | 0.684 | 0.746 |
| V1 decompose | 0.365 | 0.599 | 0.687 |
| V2 hybrid | 0.418 | 0.652 | 0.718 |
| **V3 rerank (shipped)** | **0.467** | **0.698** | **0.782** |
| V4 outcome-aware | 0.397 | 0.623 | 0.672 |
| V8 corrective | 0.412 | 0.603 | 0.683 |

The hypothesis is **refuted**. V1 is below V0 for every persona, including the ≥ 4-requirement
subset (ai_engineer 0.272 vs 0.364). On real posts, the extracted requirements are often
boilerplate sentences, and merging one retrieval per sentence dilutes the ranking.

The V8 ablation (one component removed at a time):

| Removed | Recall@5 change |
|---|---|
| rerank | −0.054 |
| hybrid | ≈ 0 |
| decomposition | +0.032 |
| corrective loop | +0.055 |

The cross-encoder is the only component that clearly earns its cost.

**Outcome-aware ranking (V4) hurts** (−0.056 vs V0). With silver relevance, items boosted for
past wins are not more relevant. This is partly a label artefact: the labels cannot see outcome.

**Claim verification (B3):** unsupported claims per proposal fell from 0.37 / 0.47 / 0.15 before
verification to 0.00 / 0.00 / 0.00 after (ai / web / data; `decision_dev_*`). Measured with the
template writer; the LLM writer's rate is **[TODO]**.

**Shipped choice:** V3. It is best on every pooled metric, but only +1.4 Recall@5 over V0, at
retrieval p95 4.6–13.3 s vs 0.2–0.8 s. If the latency budget tightens, the fallback is V0, set in
`retrieval.variant` (config only).

**Where better retrieval did not mean a better reply rate:** GigSim outcomes moved the other way.

| Persona | Hashing embedder: bids, reply rate | Shipped V3: bids, reply rate |
|---|---|---|
| ai_engineer | 33, 0.273 | 50, 0.080 |
| web_fullstack | 40, 0.300 | 46, 0.283 |
| data_analyst | 27, 0.259 | 27, 0.222 |

Sources: `iterations/outcomes_hashing_retrieval/` vs `gigsim_outcomes_dev_*_20261115-16*/17*.json`.

This comparison is **confounded**: the `zero_budget` severity change (iteration 6) landed between the two runs. Most of the extra ai_engineer bids are fixed-price posts with no stated budget, which were skipped before. LocalSim's reply model rewards price fit, and these jobs have no budget to fit, so they rarely get replies (Connects per reply 41 → 100). Better evidence ranking does not help when the bid decision admits weaker jobs. An unconfounded run (V0 vs V3 with everything else fixed) is the next experiment.

## 5. R&D question C — single agent vs supervisor vs graph
**[TODO: run]** `MODEL_PROFILE=open_small python -m evals.runners.architecture_compare --dataset
dev_web_fullstack --limit 50`. On CPU this takes hours; a GPU or hosted provider is recommended.

## 6. The change request
**[TODO: you]** Describe the 2 Nov GigSim policy update, the diff (`git diff <before>..<after> --stat`)
and the time it took. Evidence that rules are configuration: risk patterns, severities, scam flags,
the below-floor skip and policy rules all live in `agent/config.yaml`. For example, iteration 6
(lowering `zero_budget` severity) was a 3-line config change with no code edit (commit 4c93e4a).
`tests/unit/test_risk_config.py::test_new_rule_is_config_only` shows a new scam rule added through
config alone.

## 7. Signature extension — X2 proposal A/B test
Pre-registered design in `docs/EXTENSION.md` (committed before the run). Offline-writer results
(`ab_dev_*_20261115-*.json`): no significant difference for any persona (p = 0.22–0.80). The
power analysis needs 163 jobs per arm for a 30 → 45 % effect; the dev sets give ≈ 12–24 bids per
arm. The test is **underpowered**, and is reported as a null result with its CI.

## 8. Failure analysis
`python -m evals.runners.failure_taxonomy` → `evals/results/failure_taxonomy.md`. Each failed
baseline job is followed through the fix iterations (same dev set v1, same job ids):

| Failure category | Failed at baseline | Fixed by (iteration) | Still failing |
|---|---|---|---|
| missed evidence (fit too low) | 114 | taxonomy 26, tag strength 33 | 55 |
| risk false positive (auto-skip) | 59 | risk config 23 | 36 (`zero_budget` on fixed jobs; iteration 6 lowers it, measured on dev v2 only) |
| wrong bid | 44 | below-floor skip 43 | 1 |
| mispriced | 37 | below-floor skip 26 | 11 |
| scam missed | 30 | risk config 21 | 9 (subtle corporate-style fakes) |
| scam false positive | 23 | intent-required rules 18 | 5 |
| bid vs watch | 23 | — | 23 |
| injection followed | 0 | — | — |

Notable failures:

1. **Hourly posts without a rate auto-skipped.** Fixed by `unspecified_rate`.
2. **"Build a Telegram bot" / "PayPal integration" flagged as off-platform scams.** Fixed by intent
   rules.
3. **Template scams with de-punctuated emails ("julie64yahoocom") missed.** Fixed by an income-bait
   pattern.
4. **Umbrella-vs-specific skills ("Machine Learning" vs XGBoost) scored fit ≈ 0.** Fixed by the
   taxonomy.
5. **Jobs far below the floor were bid at the floor.** Fixed by the below-floor skip. Its ratios
   equal the rubric's, so part of that gain is by construction.
6. **"excellent" tagged as Excel** (data bug). Fixed in the lexicon and dev set v2.

Regressions: 18 failure instances on jobs that were correct at baseline (10 bid vs watch, 5 mispriced,
3 wrong bid).

**Label disagreement:** the rubric labels single-skill posts ("PowerBI Task") `watch` where a human
would probably bid. The rubric was deliberately *not* changed after seeing system output.
**[TODO: you]** hand-label these.

## 9. Safety and platform respect
Enforced in code:

- Untrusted text is fenced.
- Injection canaries are checked.
- Rule-detected scam flags cannot be removed by an LLM.
- Compliance strips contact details, guarantees and invented claims.
- PII is masked in logs.
- OAuth tokens are encrypted.
- No scraping or browser automation; live mode creates drafts only.

Measured: 0 of 30 planted injections followed (`decision_dev_*`). What still gets through:
subtle fake postings with corporate language (scam recall 0.5–0.7), and injections phrased as
ordinary client requirements. **[TODO]** report attack success rate before/after defences with an
LLM writer.

## 10. Hidden test results
**[TODO: after the instructor's run]** against the declared budgets in section 1.

## Appendix: reproducing every number
```bash
bash scripts/download_datasets.sh && make data && python -m datapipe.silver_labels
python -m evals.runners.rag_eval --dataset dev_<persona> --variants all --ablate v8_corrective
MODEL_PROFILE=offline python -m evals.runners.decision_eval --dataset dev_<persona>
MODEL_PROFILE=offline python -m evals.runners.gigsim_outcomes --dataset dev_<persona> --limit 1000 --wait-s 0
python -m evals.runners.failure_taxonomy && python -m evals.runners.results_table
```
