# GigBid R&D report (max 10 pages)

Every number cites a file in `evals/results/`. Write the hypothesis before each experiment.

## 1. System in one page
Architecture figure (`docs/ARCHITECTURE.md`), the marketplace port, what the human approves.

## 1b. Data
Sources and licences, real vs synthetic (docs/DATA_CARD.md), counts from provenance.json,
labelling procedure and its limits, and what LocalSim's reply model can and cannot tell you.

## 2. Retrieval (B2, B4)
Hypothesis: ___. Table: V0, V1, V2, V3, V4, V8 x personas: Recall@5, MRR, nDCG@10, p95 latency
(`rag_<dataset>_*.json`). Separate column for jobs with >= 4 requirements. Ablation of the
shipped pipeline (`--ablate`). Which variant ships and why (cost and latency included).

## 3. Grounding (B3)
Unsupported claims per proposal before vs after verification; examples of each label; one
case where verification removed something true (over-reach) and what you changed.

## 4. Judge calibration
30 human labels vs judge: weighted kappa per criterion (`judge_calibration_*.json`). Whether the
judge is trusted for later tables, and its known biases.

## 5. R&D question A: tool granularity and descriptions
Hypothesis: ___. 40 tasks (`evals/datasets/tool_tasks.json`), conditions fine / coarse /
terse_docs: tool accuracy, argument accuracy, wrong calls, tokens (`toolgran_*.json`).
What you changed in the shipped tool set because of it.

## 6. R&D question C: architecture
Hypothesis: ___. ReAct vs supervisor vs graph on 50 dev jobs (`arch_*.json`): F1, scam recall,
injections followed, unsupported claims, steps, tokens, latency. When the graph's structure paid
for itself and when it did not.

## 7. Decisions, pricing, outcomes
Bid/skip F1, scam precision/recall, price in fair band (`decision_*.json`); GigSim reply and hire
rate, Connects per reply (`gigsim_outcomes_*.json`). Latency/cost vs the declared budgets.

## 8. Extension (X2)
Summary of docs/EXTENSION.md results.

## 9. Failure taxonomy
>= 10 failed dev jobs (`evals/labels/failures_*.csv`): category counts, two worked examples,
what you fixed and what you did not.

## 10. Limits and what you would do next
Including what the in-memory GigSim stand-in and the fixtures could not tell you.
