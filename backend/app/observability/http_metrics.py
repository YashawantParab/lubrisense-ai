"""Central HTTP-request metrics (Phase 26 brief §26.2) — request count by status class,
error count, and mean latency across every `/api/v1/*` route. Deliberately reuses
`WorkerMetrics` (the same flat counter/gauge object every worker/package already renders
its own `/metrics` from) rather than adding a labeled-metrics dependency — see
`app.observability.metrics` module docstring for why. Exposed at `GET
/api/v1/system/metrics`, alongside the existing per-package `/metrics` routes
(`/incidents/metrics`, `/maintenance/cases/metrics`, `/knowledge/metrics`,
`/agent/metrics`).
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.observability.metrics import WorkerMetrics

#: shared with app.api.deps, which increments `auth_failures_total` directly on this
#: same object (Phase 24/26) so every HTTP-adjacent counter renders from one
#: `GET /api/v1/system/metrics` endpoint.
HTTP_METRICS = WorkerMetrics()


def _status_class(status_code: int) -> str:
    return f"{status_code // 100}xx"


class HTTPMetricsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Callable) -> None:  # type: ignore[type-arg]
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            HTTP_METRICS.increment("http_requests_total")
            HTTP_METRICS.increment("http_requests_total_5xx")
            HTTP_METRICS.increment("http_requests_errors_total")
            raise
        elapsed = time.perf_counter() - start

        HTTP_METRICS.increment("http_requests_total")
        HTTP_METRICS.increment(f"http_requests_total_{_status_class(response.status_code)}")
        if response.status_code >= 500:
            HTTP_METRICS.increment("http_requests_errors_total")

        counters, gauges = HTTP_METRICS.snapshot()
        total = counters.get("http_requests_total", 1)
        previous_avg = gauges.get("http_request_duration_seconds_avg", 0.0)
        # Incremental mean update — avoids storing every sample just to render one gauge.
        new_avg = previous_avg + (elapsed - previous_avg) / total
        HTTP_METRICS.set_gauge("http_request_duration_seconds_avg", new_avg)

        return response
