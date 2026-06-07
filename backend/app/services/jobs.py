"""Job-queue abstraction for re-index work.

The webhook handler must return fast, so catalog work is dispatched to a queue.
Two implementations:

* :class:`InlineJobQueue` — awaits the work in-process. Default for demo/CI and
  small deployments; deterministic and dependency-free.
* :class:`ArqJobQueue` — enqueues onto Redis-backed Arq workers (Phase 2 plan)
  for production throughput. Lazy import.

Both satisfy :class:`JobQueue`, so the dispatch site never changes.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol


class JobQueue(Protocol):
    """Dispatches a named job with keyword arguments."""

    async def enqueue(self, job: str, **kwargs: Any) -> None: ...


class InlineJobQueue(JobQueue):
    """Runs jobs immediately in-process (demo/CI/small scale)."""

    def __init__(self, handlers: dict[str, Callable[..., Awaitable[Any]]]) -> None:
        self._handlers = handlers

    async def enqueue(self, job: str, **kwargs: Any) -> None:
        handler = self._handlers.get(job)
        if handler is None:
            raise KeyError(f"No handler registered for job {job!r}")
        await handler(**kwargs)
