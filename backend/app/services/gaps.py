"""Feedback → content-gap loop (DEVELOPMENT_PLAN.md §8.2).

Turns observed failures into a ranked list of content gaps the merchant can fix
with one click. A gap is a cluster of customer questions that either triggered a
low-confidence/out-of-scope handoff or received a thumbs-down. Questions are
clustered by normalized content-word overlap (Jaccard) so near-duplicates merge.
Each gap surfaces example questions, a count, and a suggested FAQ title — the
admin "create FAQ" action feeds :class:`ContentService`, which re-indexes it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models.conversation import Conversation, MessageRole
from app.repositories.base import ConversationRepository

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "do",
        "does",
        "i",
        "my",
        "to",
        "of",
        "for",
        "how",
        "what",
        "can",
        "you",
        "your",
        "me",
        "in",
        "on",
        "it",
        "with",
    }
)
_JACCARD_MERGE = 0.5  # clusters merge above this token-overlap


@dataclass
class ContentGap:
    """A clustered set of unanswered/poorly-answered questions."""

    suggested_title: str
    count: int
    examples: list[str] = field(default_factory=list)


def _singular(tok: str) -> str:
    # Cheap normalization so "competitor"/"competitors" cluster together.
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


def _content_tokens(text: str) -> set[str]:
    return {_singular(t) for t in _TOKEN.findall(text.lower()) if t not in _STOP}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _gap_questions(conversation: Conversation) -> list[str]:
    """Customer questions in a conversation that signal a content gap."""
    questions: list[str] = []
    messages = conversation.messages
    for i, msg in enumerate(messages):
        if msg.role is not MessageRole.ASSISTANT:
            continue
        weak = msg.handoff_reason in {"low_confidence", "out_of_scope"}
        if not weak:
            continue
        # The preceding user turn is the unanswered question.
        for prev in reversed(messages[:i]):
            if prev.role is MessageRole.USER:
                questions.append(prev.content)
                break
    return questions


class ContentGapService:
    """Clusters weak-answer signals into ranked, actionable content gaps."""

    def __init__(self, repo: ConversationRepository) -> None:
        self._repo = repo

    async def compute(self, *, limit: int = 500) -> list[ContentGap]:
        conversations = await self._repo.list_conversations(limit=limit)
        questions: list[str] = []
        for conv in conversations:
            questions.extend(_gap_questions(conv))
        return self._cluster(questions)

    @staticmethod
    def _cluster(questions: list[str]) -> list[ContentGap]:
        clusters: list[tuple[set[str], list[str]]] = []
        for q in questions:
            tokens = _content_tokens(q)
            if not tokens:
                continue
            placed = False
            for ctoks, examples in clusters:
                if _jaccard(tokens, ctoks) >= _JACCARD_MERGE:
                    ctoks |= tokens
                    examples.append(q)
                    placed = True
                    break
            if not placed:
                clusters.append((tokens, [q]))
        gaps = [
            ContentGap(
                suggested_title=examples[0],
                count=len(examples),
                examples=examples[:5],
            )
            for _, examples in clusters
        ]
        gaps.sort(key=lambda g: g.count, reverse=True)
        return gaps
