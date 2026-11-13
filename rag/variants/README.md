# Retrieval variants

Every variant is a flag set over `rag/pipeline.py` (cumulative, so each step's gain is measurable):

| ID | File | Flags | Group |
|----|------|-------|-------|
| V0 | v0_naive.py | dense on whole post | Baseline (required) |
| V1 | v1_decompose.py | decompose | Query (required) |
| V2 | v2_hybrid.py | decompose + hybrid | Retrieval (required) |
| V3 | v3_rerank.py | + rerank | Retrieval (required) |
| V4 | v4_outcome.py | + outcome_aware | Ranking |
| V8 | v8_corrective.py | V3 + corrective | Agentic (required: one of V8/V9) |

`python -m evals.runners.rag_eval --variants all` reruns the comparison; `--ablate v8_corrective`
removes one component at a time from the chosen pipeline. The shipped variant is
`retrieval.variant` in agent/config.yaml and must be the one the results file supports.
