| category | failed at baseline | fixed (by iteration) | not fixed |
|---|---|---|---|
| bid_vs_watch | 23 | - | 23 |
| mispriced | 37 | 4_below_floor_skip: 26 | 11 |
| missed_evidence (fit too low) | 114 | 1_risk_config_taxonomy: 26, 3_tag_strength: 33 | 55 |
| risk_false_negative (scam missed) | 30 | 1_risk_config_taxonomy: 21 | 9 |
| risk_false_positive (scam) | 23 | 2_intent_scam_rules: 18 | 5 |
| risk_false_positive (skip) | 59 | 1_risk_config_taxonomy: 23 | 36 |
| wrong_bid | 44 | 4_below_floor_skip: 43 | 1 |

Regressions at iteration 4 (jobs correct at baseline, wrong at the end): {'wrong_bid': 3, 'mispriced': 5, 'bid_vs_watch': 10}
