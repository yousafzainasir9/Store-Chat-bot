"""Eval gate as a unit test (eval-gated prompt deploys, DEVELOPMENT_PLAN.md §9).

Runs the offline evaluation in-process and asserts the active prompt + retrieval
stack meet the committed thresholds. A prompt change that regresses retrieval or
answer/refusal quality fails CI here, so it can never deploy.
"""

from __future__ import annotations

import pytest
from eval.run_eval import run

pytestmark = pytest.mark.asyncio

# Offline-calibrated floors; raise these once the production embedding model +
# cross-encoder are connected and re-baselined.
_MIN_RECALL = 0.85
_MIN_ANSWER = 0.90
_MIN_REFUSAL = 0.90


async def test_active_prompt_passes_eval_gate() -> None:
    metrics = await run(k=5)
    assert metrics["recall_at_k_reranked"] >= _MIN_RECALL
    assert metrics["answer_accuracy"] >= _MIN_ANSWER
    assert metrics["refusal_accuracy"] >= _MIN_REFUSAL
    # Reranking must not hurt retrieval.
    assert metrics["recall_at_k_reranked"] >= metrics["recall_at_k_vector"]
    assert metrics["n_cases"] >= 100
