"""HTTP middleware: request-id binding, access logging, and timing.

Generates (or honours an inbound) ``X-Request-ID``, binds it to the logging
context var so every log line in the request is correlated, records request
latency into the metrics registry, and echoes the id back on the response.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.observability.logging import get_logger, request_id_var
from app.observability.metrics import metrics

_REQUEST_ID_HEADER = "X-Request-ID"
_log = get_logger("http")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind a request id, time the request, and emit one structured access log."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(_REQUEST_ID_HEADER) or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[_REQUEST_ID_HEADER] = request_id
            return response
        finally:
            elapsed = time.perf_counter() - start
            metrics.observe("http_request_seconds", elapsed)
            metrics.incr(f"http_responses_total.{status_code // 100}xx")
            _log.info(
                "request",
                method=request.method,
                path=request.url.path,
                status=status_code,
                duration_ms=round(elapsed * 1000, 2),
            )
            request_id_var.reset(token)
