# Signature extension: X2, A/B testing of proposal strategies

> Fill in sections 1-3 and commit them BEFORE running the experiment (pre-registration). The commit
> timestamp is your evidence that the hypothesis came first.

## 1. Hypothesis (pre-registered)
Strategy B (`writer_b`: open with one sharp question about the client's problem) gets a higher
GigSim reply rate than strategy A (`writer`: open by restating the problem, then evidence).
H0: reply_rate(B) = reply_rate(A). Two-sided, alpha = 0.05.

Simulator caveat: outcomes come from LocalSim's documented reply model, which scores specificity,
skills coverage, price fit and generic phrasing. State that the test measures which strategy the
simulator prefers, and why that is or is not informative.

## 2. Design
* Arms: A = `agent/prompts/writer.md`, B = `agent/prompts/writer_b.md` (config `writer.strategy`).
  Everything else identical: same jobs pool, model profile, retrieval variant, pricing.
* Assignment: `sha256(job_id) % 2` (`evals/runners/ab_test.py: arm_of`), so no cherry-picking.
* Primary metric: reply rate per submitted proposal. Secondary: judge `overall` score (only if the
  judge's calibration kappa >= 0.6), Connects per reply.
* Sample size: `python -m evals.runners.ab_test --dataset x --power <baseline> <baseline+effect>`.
  Expected baseline: 0.30 (offline-writer reply rate, `gigsim_outcomes_*` pilot). Minimum effect worth
  detecting: 15 points. Jobs needed per arm: **163**. The dev sets supply only 11-24 bids per arm, so
  the test is underpowered and the CI is the main result. (These three lines were filled in after
  the run; the hypothesis and design above were committed before it, in 1dbbc90 vs af2aa96.)
* Stopping rule: run once at the planned n. No peeking, no early stop.

## 3. Analysis plan
Two-proportion z-test and a bootstrap 95% CI of the difference (B - A). Report both arms' n,
replies, rate, p-value, CI. A null result is reported as a null result.

## 4. Results (after the run)
Run: `MODEL_PROFILE=offline python -m evals.runners.ab_test --dataset dev_<persona> --limit 1000 --wait-s 0`
(commit af2aa96). Template writer (no LLM), hashing embedder, LocalSim reply model. Files:
`evals/results/ab_dev_*_20261115-*.json`.

| Persona | A bids | A replies (rate) | B bids | B replies (rate) | p (two-sided) | 95% CI of B − A |
|---|---|---|---|---|---|---|
| ai_engineer | 15 | 3 (0.200) | 18 | 3 (0.167) | 0.80 | [−0.29, 0.22] |
| web_fullstack | 24 | 7 (0.292) | 16 | 2 (0.125) | 0.22 | [−0.40, 0.08] |
| data_analyst | 16 | 5 (0.313) | 11 | 4 (0.364) | 0.78 | [−0.29, 0.41] |

No significant difference in any persona. Every CI includes 0 and spans more than 50 points. The
judge `overall` score is not reported: the judge has no calibration yet (kappa needs 30 human labels).

## 5. What we would ship and why
Strategy A stays the default (`writer.strategy: writer`). B did not beat it. At this sample size a
null result is uninformative rather than evidence of no effect, so A wins as the incumbent, not on
merit. To get a real answer: run the LLM writer on ≥ 163 bids per arm (pool more GigSim jobs, or
pool personas, accepting persona as a covariate), and report the result even if it stays null.
