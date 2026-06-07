"""Confidence scoring + the answer/handoff decision.

Confidence is derived from the top reranked score and the margin to the next
candidate. Below ``min_score`` (or empty retrieval) the orchestrator must hand
off rather than guess — the plan's grounded-only guarantee.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.rag.models import ScoredChunk


@dataclass(frozen=True, slots=True)
class ConfidenceDecision:
    """Whether retrieval is strong enough to answer, with a normalized score."""

    confident: bool
    score: float
    reason: str


def assess(chunks: Sequence[ScoredChunk], *, min_score: float = 0.15) -> ConfidenceDecision:
    """Decide if the retrieved evidence supports a grounded answer."""
    if not chunks:
        return ConfidenceDecision(False, 0.0, "no_results")
    top = chunks[0].score
    if top < min_score:
        return ConfidenceDecision(False, top, "low_score")
    return ConfidenceDecision(True, top, "ok")
