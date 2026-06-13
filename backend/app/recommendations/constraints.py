"""Extract recommendation constraints from the conversation.

Fashion recommendations must respect what the customer has told us — budget,
size, color, gender, category, and occasion — gathered across the whole
conversation, not just the latest turn. This module is pure and deterministic so
it is trivially testable and adds no latency.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

# Catalog vocabulary (kept in sync with the synthetic catalog + typical stores).
_CATEGORIES = {
    "dress": "Dress",
    "dresses": "Dress",
    "shirt": "Shirt",
    "shirts": "Shirt",
    "jeans": "Jeans",
    "sweater": "Sweater",
    "sweaters": "Sweater",
    "jumper": "Sweater",
    "jacket": "Jacket",
    "jackets": "Jacket",
    "skirt": "Skirt",
    "skirts": "Skirt",
}
_COLORS = ["black", "white", "navy", "blue", "olive", "green", "burgundy", "red", "beige"]
_SIZE_WORDS = {"extra small": "XS", "small": "S", "medium": "M", "large": "L", "extra large": "XL"}
_OCCASIONS = ["wedding", "work", "office", "casual", "party", "beach", "gym", "date", "formal"]

_BUDGET_RANGE = re.compile(r"\$?(\d{1,4})\s*(?:-|to|and)\s*\$?(\d{1,4})")
_BUDGET_MAX = re.compile(r"(?:under|below|less than|max|up to|cheaper than)\s*\$?(\d{1,4})", re.I)
_BUDGET_AROUND = re.compile(r"(?:around|about|approx(?:imately)?|~)\s*\$?(\d{1,4})", re.I)
# A bare price-like number (e.g. "54 shirts", "shirt for 54") when paired with a
# product category. Excludes numbers that are a size ("size 10") or quantity-ish
# single digits.
_BARE_NUMBER = re.compile(r"(?<![\w$])(\d{2,4})(?![\w%])")
_SIZE_PREFIX = re.compile(r"size\s*$", re.I)
_SIZE_LETTER = re.compile(r"\bsize\s*(xs|s|m|l|xl|xxl)\b", re.I)
_GENDER_MEN = re.compile(r"\b(men'?s?|mens|for him|male)\b", re.I)
_GENDER_WOMEN = re.compile(r"\b(women'?s?|womens|ladies|for her|female)\b", re.I)


@dataclass(frozen=True, slots=True)
class Constraints:
    """Structured recommendation constraints (any field may be None/empty)."""

    category: str | None = None
    color: str | None = None
    size: str | None = None
    gender: str | None = None
    occasion: str | None = None
    budget_min: float | None = None
    budget_max: float | None = None

    def merged_with(self, other: Constraints) -> Constraints:
        """Overlay ``other`` (newer) onto ``self`` (older); newer wins per field."""
        return Constraints(
            category=other.category or self.category,
            color=other.color or self.color,
            size=other.size or self.size,
            gender=other.gender or self.gender,
            occasion=other.occasion or self.occasion,
            budget_min=other.budget_min if other.budget_min is not None else self.budget_min,
            budget_max=other.budget_max if other.budget_max is not None else self.budget_max,
        )


def _extract_budget(text: str) -> tuple[float | None, float | None]:
    m = _BUDGET_RANGE.search(text)
    if m:
        lo, hi = sorted((float(m.group(1)), float(m.group(2))))
        return lo, hi
    m = _BUDGET_MAX.search(text)
    if m:
        return None, float(m.group(1))
    m = _BUDGET_AROUND.search(text)
    if m:
        target = float(m.group(1))
        return target * 0.8, target * 1.2
    return None, None


def _extract_size(text: str) -> str | None:
    m = _SIZE_LETTER.search(text)
    if m:
        return m.group(1).upper()
    low = text.lower()
    for word, letter in _SIZE_WORDS.items():
        if re.search(rf"\b{word}\b", low):
            return letter
    return None


def extract_constraints(text: str) -> Constraints:
    """Extract constraints from a single message."""
    low = text.lower()
    category = next((v for k, v in _CATEGORIES.items() if re.search(rf"\b{k}\b", low)), None)
    color = next((c.title() for c in _COLORS if re.search(rf"\b{c}\b", low)), None)
    occasion = next((o for o in _OCCASIONS if re.search(rf"\b{o}\b", low)), None)
    gender = "men" if _GENDER_MEN.search(text) else "women" if _GENDER_WOMEN.search(text) else None
    budget_min, budget_max = _extract_budget(text)
    size = _extract_size(text)
    # "54 shirts" / "shirt for 54": a bare number next to a product means a price
    # ceiling. Only when we have a category, no explicit budget, and the number
    # isn't a size value.
    if category and budget_min is None and budget_max is None:
        for m in _BARE_NUMBER.finditer(text):
            if _SIZE_PREFIX.search(text[: m.start()]):
                continue  # it's a numeric size ("size 10"), not a price
            budget_max = float(m.group(1))
            break
    return Constraints(
        category=category,
        color=color,
        size=size,
        gender=gender,
        occasion=occasion,
        budget_min=budget_min,
        budget_max=budget_max,
    )


def extract_constraints_from_history(texts: Sequence[str]) -> Constraints:
    """Accumulate constraints across the conversation (older first)."""
    merged = Constraints()
    for text in texts:
        merged = merged.merged_with(extract_constraints(text))
    return merged
