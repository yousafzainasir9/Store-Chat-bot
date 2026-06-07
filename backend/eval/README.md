# Evaluation harness

Phase 0 placeholder. From Phase 1 this directory holds:

- `dataset.jsonl` — curated Q/A pairs per intent (FAQ, policy, size, product,
  order, return, recommendation, visual, out-of-scope) with expected sources and
  ideal answers.
- `run_eval.py` — scores **retrieval** (recall@k, MRR before/after reranking) and
  **answers** (groundedness/faithfulness, correctness, citation accuracy,
  refusal correctness).
- The CI gate (Phase 8) fails the build when metrics regress below threshold, and
  a prompt change must pass this gate before deploy (see DEVELOPMENT_PLAN.md §9).
