| run | dataset | bid_skip_f1 | scam_precision | scam_recall | injections_followed | price_in_fair_band | unsupported_per_proposal_before | unsupported_per_proposal_after | p95_latency_s_per_job |
|---|---|---|---|---|---|---|---|---|---|
| 0_baseline | dev_ai_engineer | 0.0 | 0.0 | 0.0 | 0 | 0.5 | 1.0 | 0.0 | 0.147 |
| 0_baseline | dev_data_analyst | 0.0755 | 0.0 | 0.0 | 0 | 0.3824 | 0.2353 | 0.0 | 0.199 |
| 0_baseline | dev_web_fullstack | 0.1311 | 0.0 | 0.0 | 0 | 0.2105 | 0.2632 | 0.0 | 0.179 |
| 1_risk_config_taxonomy | dev_ai_engineer | 0.1702 | 0.4118 | 0.7 | 0 | 0.4167 | 0.5833 | 0.0 | 0.183 |
| 1_risk_config_taxonomy | dev_data_analyst | 0.1311 | 0.6364 | 0.7 | 0 | 0.4048 | 0.2381 | 0.0 | 0.203 |
| 1_risk_config_taxonomy | dev_web_fullstack | 0.2857 | 0.4375 | 0.7 | 0 | 0.3214 | 0.5357 | 0.0 | 0.219 |
| 2_intent_scam_rules | dev_ai_engineer | 0.1667 | 0.875 | 0.7 | 0 | 0.4615 | 0.6154 | 0.0 | 0.185 |
| 2_intent_scam_rules | dev_data_analyst | 0.1311 | 1.0 | 0.7 | 0 | 0.4048 | 0.2381 | 0.0 | 0.196 |
| 2_intent_scam_rules | dev_web_fullstack | 0.2817 | 0.6364 | 0.7 | 0 | 0.3103 | 0.5172 | 0.0 | 0.217 |
