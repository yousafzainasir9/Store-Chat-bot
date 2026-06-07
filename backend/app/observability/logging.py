"""Structured logging configuration.

Uses ``structlog`` to emit machine-parseable JSON in deployed environments and
human-friendly console output in local development. A request-id is bound to a
context var so every log line within a request is correlated.

PII note: per the plan's security posture, never log raw customer messages,
emails, or order numbers at INFO level. Use the ``redact`` helper for any field
that may carry PII before it reaches a log call.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog

# Correlates all log lines emitted while handling a single request.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def _add_request_id(
    _logger: structlog.types.WrappedLogger,
    _method: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Bind the current request id (if any) onto every log line."""
    rid = request_id_var.get()
    if rid is not None:
        event_dict["request_id"] = rid
    return event_dict


def configure_logging(*, level: str = "INFO", json_output: bool = True) -> None:
    """Configure stdlib logging + structlog once at startup.

    Args:
        level: Minimum log level name (e.g. ``"INFO"``).
        json_output: Emit JSON (deployed) when True; pretty console when False.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_request_id,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging (uvicorn, sqlalchemy, etc.) through the same level.
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level)
    for noisy in ("uvicorn.access",):
        logging.getLogger(noisy).setLevel(max(log_level, logging.WARNING))


def get_logger(name: str | None = None) -> Any:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)


def redact(value: str | None, *, keep: int = 0) -> str:
    """Redact a potentially-sensitive value for safe logging.

    Args:
        value: The raw value (may be ``None``).
        keep: Number of trailing characters to keep visible.

    Returns:
        A masked string such as ``"***"`` or ``"***1234"``.
    """
    if not value:
        return "***"
    if keep <= 0 or keep >= len(value):
        return "***"
    return "***" + value[-keep:]
