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
  Expected baseline: ___ (from a pilot). Minimum effect worth detecting: ___ points.
  Jobs needed per arm: ___. If GigSim cannot supply that many, say so and report the CI only.
* Stopping rule: run once at the planned n. No peeking, no early stop.

## 3. Analysis plan
Two-proportion z-test and a bootstrap 95% CI of the difference (B - A). Report both arms' n,
replies, rate, p-value, CI. A null result is reported as a null result.

## 4. Results (after the run)
| Arm | Bids | Replies | Reply rate | Judge overall |
|---|---|---|---|---|
| A writer | | | | |
| B writer_b | | | | |

p = ___, 95% CI of difference = [___, ___]. Results file: `evals/results/ab_<dataset>_<timestamp>.json`.

## 5. What we would ship and why
