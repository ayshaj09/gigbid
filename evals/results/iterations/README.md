# Decision-eval iterations on the real dev sets (offline profile, silver_rubric_v2 labels)

Each folder is one full run of `python -m evals.runners.decision_eval --dataset dev_<persona>`
after one change, so every fix in the failure analysis has a before and after.

| Run | Change (commit) |
|---|---|
| 0_baseline | system as built on fixtures; first run on Kaggle data (8e7ba2f) |
| 1_risk_config_taxonomy | risk rules in config, hourly-without-rate no longer `zero_budget`, income-bait / de-punctuated email patterns (38e1c26); skill taxonomy in Fit Matcher (f14acff) |
| 2_intent_scam_rules | contact / payment / credential rules require intent toward the freelancer (8350d24) |
| 3_tag_strength | skill requirements scored against evidence skill tags via the taxonomy |
| 4_below_floor_skip | skip jobs paying < 50% of the project floor or < 60% of the hourly rate (43f6854). Same ratios as the silver rubric's budget rule, so part of this gain is **by construction** |
| 5_lexicon_fix_dev_v2 | skill-lexicon bug fixed (0cb7d6c) and dev sets rebuilt (e339cd9): **dev set v2**, so compare 5+ with each other, not with 0-4 |

Summaries: `python -m evals.runners.summarise_iterations` → `evals/results/iterations/summary.csv`.
| 6_zero_budget_severity | fixed-price posts with no stated budget: severity 0.6 -> 0.35 in config (config-only change) |
