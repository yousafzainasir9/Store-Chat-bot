"""Lightweight Phase-1 guardrails: PII redaction + prompt-injection screening.

This is the *baseline*; the full posture (moderation, tool allow-listing,
post-generation grounding checks) is built out in Phase 8. The principle from
the plan holds from day one: retrieved content and user input are untrusted, and
PII is kept out of logs/traces.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\d .-]{7,}\d)(?!\d)")
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){13,16}(?!\d)")

# Common prompt-injection patterns. Detection -> we fence/flag, never obey.
_INJECTION = re.compile(
    r"("
    r"ignore (?:all |the )?(?:previous|prior|above) (?:instructions|prompts?)"
    r"|disregard (?:the |all )?(?:previous |above )?(?:system )?(?:prompt|instructions)"
    r"|forget (?:all |your )?(?:previous |prior )?instructions"
    r"|you are now"
    r"|reveal (?:your |the )?(?:system )?(?:prompt|instructions)"
    r"|(?:print|show|repeat|output) (?:your |the )?(?:system )?(?:prompt|instructions)"
    r"|act as"
    r"|pretend (?:to be|you are)"
    r"|developer mode|jailbreak|DAN mode"
    r"|new (?:instructions|system prompt)"
    r"|override (?:your |the )?(?:instructions|rules|safety)"
    r"|do anything now"
    r")",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class GuardResult:
    """Outcome of screening a user message."""

    sanitized: str
    injection_detected: bool


def redact_pii(text: str) -> str:
    """Mask emails, phone numbers, and card-like numbers for safe logging."""
    text = _EMAIL.sub("[email]", text)
    text = _CARD.sub("[card]", text)
    text = _PHONE.sub("[phone]", text)
    return text


def screen_input(text: str) -> GuardResult:
    """Screen an inbound user message.

    We do not mutate the user's wording (they may legitimately quote a phrase),
    but we flag injection so the orchestrator can fence retrieved/user content
    and keep system instructions non-overridable.
    """
    return GuardResult(sanitized=text.strip(), injection_detected=bool(_INJECTION.search(text)))
