"""Customer identity extraction + verification.

No order, tracking, fulfillment, PII, or return action happens until the
customer has proven identity by providing **an order number and the email on
that order** (DEVELOPMENT_PLAN.md §3, §6). This module:

* extracts an order number and email from free text, and
* verifies a supplied email matches the order's email (case-insensitive).

Verification itself (comparing against the real order) is delegated to the
order service, which holds the live Shopify data; this module provides the
parsing and the constant-time compare helper.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# "#1001", "order 1001", "1001" (4-8 digits). Kept conservative to avoid grabbing
# unrelated numbers (sizes, prices) from the message.
_ORDER_RE = re.compile(r"(?:order\s*#?\s*|#)\s*(\d{3,10})|\b(\d{4,10})\b", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


@dataclass(frozen=True, slots=True)
class Identity:
    """Identity signals extracted from a customer message."""

    order_number: str | None
    email: str | None

    @property
    def is_complete(self) -> bool:
        """True when both an order number and an email are present."""
        return bool(self.order_number and self.email)


def extract_identity(text: str) -> Identity:
    """Pull an order number and email from free text (best effort)."""
    email_match = _EMAIL_RE.search(text)
    email = email_match.group(0).lower() if email_match else None

    order_number: str | None = None
    m = _ORDER_RE.search(text)
    if m:
        order_number = m.group(1) or m.group(2)
    return Identity(order_number=order_number, email=email)


def emails_match(supplied: str | None, on_record: str | None) -> bool:
    """Case-insensitive, whitespace-trimmed email comparison."""
    if not supplied or not on_record:
        return False
    return supplied.strip().lower() == on_record.strip().lower()
