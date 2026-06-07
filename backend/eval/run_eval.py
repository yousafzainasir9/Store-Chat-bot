"""Evaluation harness for the RAG pipeline.

Measures, against ``eval/dataset.jsonl``:

* Retrieval  — recall@k and MRR of the expected source, before vs. after rerank.
* Answering  — groundedness/refusal correctness: answerable questions produce a
  cited answer containing the expected substring; out-of-scope and injection
  questions are correctly refused/handed off.

Runs fully offline against the deterministic demo stack (no API keys). In CI
(Phase 8) thresholds here become a build gate; a prompt change must pass before
deploy (DEVELOPMENT_PLAN.md §9).

Usage:
    python -m eval.run_eval [--k 5] [--min-recall 0.8] [--min-answer 0.9]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from app.config import Environment, Settings
from app.rag.reranker import OverlapReranker
from app.services.container import build_container

_DATASET = Path(__file__).resolve().parent / "dataset.jsonl"


@dataclass
class Case:
    id: str
    intent: str
    question: str
    expected_source: str | None
    expect_answer: bool
    must_include: list[str]


def _load_cases() -> list[Case]:
    cases: list[Case] = []
    for line in _DATASET.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        cases.append(
            Case(
                id=d["id"],
                intent=d["intent"],
                question=d["question"],
                expected_source=d.get("expected_source"),
                expect_answer=d["expect_answer"],
                must_include=[s.lower() for s in d.get("must_include", [])],
            )
        )
    return cases


def _rank_of_source(sources: list[str], expected: str) -> int | None:
    for i, s in enumerate(sources):
        if s == expected:
            return i
    return None


async def _collect_answer(container, question: str) -> tuple[str, list[str], bool]:
    """Return (answer_text, citations, handed_off)."""
    text_parts: list[str] = []
    citations: list[str] = []
    handed_off = False
    async for ev in container.orchestrator.answer("eval", question):
        if ev.type == "token":
            text_parts.append(ev.text)
        elif ev.type == "handoff":
            handed_off = True
        elif ev.type == "citations":
            citations = ev.citations
    return "".join(text_parts), citations, handed_off


async def run(k: int) -> dict[str, float]:
    settings = Settings(environment=Environment.TEST, demo_mode=True, log_json=True)
    container = build_container(settings)
    await container.bootstrap()

    cases = _load_cases()
    answerable = [c for c in cases if c.expect_answer and c.expected_source]

    # --- Retrieval metrics: vector-only vs. reranked. ---
    hits_vec = hits_re = 0
    mrr_vec = mrr_re = 0.0
    raw_reranker = OverlapReranker()  # to compare "before rerank" we use raw vector order

    for c in answerable:
        qvec = (await container.embedder.embed([c.question]))[0]
        vec_candidates = await container.store.search(qvec, top_k=settings.rag_candidate_k)
        vec_sources = [sc.citation for sc in vec_candidates[:k]]
        reranked = await raw_reranker.rerank(c.question, vec_candidates, top_k=k)
        re_sources = [sc.citation for sc in reranked]

        rv = _rank_of_source(vec_sources, c.expected_source)
        rr = _rank_of_source(re_sources, c.expected_source)
        if rv is not None:
            hits_vec += 1
            mrr_vec += 1.0 / (rv + 1)
        if rr is not None:
            hits_re += 1
            mrr_re += 1.0 / (rr + 1)

    n = max(1, len(answerable))
    recall_vec, recall_re = hits_vec / n, hits_re / n
    mrr_vec, mrr_re = mrr_vec / n, mrr_re / n

    # --- Answer metrics: grounded-answer vs. correct refusal. ---
    answer_ok = 0
    refusal_ok = 0
    n_answer = sum(1 for c in cases if c.expect_answer)
    n_refusal = sum(1 for c in cases if not c.expect_answer)

    for c in cases:
        text, citations, handed_off = await _collect_answer(container, c.question)
        low = text.lower()
        if c.expect_answer:
            grounded = bool(citations) and not handed_off
            included = all(tok in low for tok in c.must_include) if c.must_include else True
            if grounded and included:
                answer_ok += 1
            else:
                print(f"  [answer miss] {c.id}: grounded={grounded} included={included}")
        else:
            if handed_off:
                refusal_ok += 1
            else:
                print(f"  [refusal miss] {c.id}: did not hand off")

    answer_acc = answer_ok / max(1, n_answer)
    refusal_acc = refusal_ok / max(1, n_refusal)

    return {
        "recall_at_k_vector": recall_vec,
        "recall_at_k_reranked": recall_re,
        "mrr_vector": mrr_vec,
        "mrr_reranked": mrr_re,
        "answer_accuracy": answer_acc,
        "refusal_accuracy": refusal_acc,
        "n_cases": float(len(cases)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="RAG evaluation")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--min-recall", type=float, default=0.85)
    parser.add_argument("--min-answer", type=float, default=0.90)
    parser.add_argument("--min-refusal", type=float, default=0.90)
    args = parser.parse_args()

    metrics = asyncio.run(run(args.k))
    print("\n=== Evaluation results ===")
    for key, value in metrics.items():
        print(f"{key:28s} {value:.3f}")

    gates = {
        "recall_at_k_reranked": args.min_recall,
        "answer_accuracy": args.min_answer,
        "refusal_accuracy": args.min_refusal,
    }
    failed = [k for k, threshold in gates.items() if metrics[k] < threshold]
    if failed:
        print(f"\nFAILED gates: {', '.join(failed)}")
        return 1
    print("\nAll gates passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
