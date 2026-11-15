# Decision-eval iterations on the real dev sets (offline profile, silver_rubric_v2 labels)

Each folder is one full run of `python -m evals.runners.decision_eval --dataset dev_<persona>`
after one change, so every fix in the failure analysis has a before and after.

| Run | Change (commit) |
|---|---|
| 0_baseline | system as built on fixtures; first run on Kaggle data (8e7ba2f) |
| 1_risk_config_taxonomy | risk rules in config, hourly-without-rate no longer `zero_budget`, income-bait / de-punctuated email patterns (38e1c26); skill taxonomy in Fit Matcher (f14acff) |
| 2_intent_scam_rules | contact / payment / credential rules require intent toward the freelancer (8350d24) |

Summaries: `python -m evals.runners.summarise_iterations` → `evals/results/iterations/summary.csv`.
