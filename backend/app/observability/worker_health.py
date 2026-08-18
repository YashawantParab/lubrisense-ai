"""Shared liveness/readiness/metrics HTTP server for background worker processes
(the MQTT bridge, telemetry consumer, and data-quality worker — none of them sit behind
FastAPI, so none of them have `/health`/`/ready`/`/metrics` for free).

A tiny, dependency-free `http.server`-based server — a second FastAPI instance would be
overkill for a process that just needs three read-only endpoints. Reuses the
liveness-vs-readiness distinction from `app.services.health_service`/ADR-021: `/health`
never touches external dependencies, `/ready` does and returns 503 if any are unavailable.

Originally `app.pipeline.health.PipelineHealthServer` (Phase 6) — relocated here in Phase 7
since the data-quality worker needs the identical server (TECHNICAL_DECISIONS.md, shared
worker infra ADR).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.observability.metrics import WorkerMetrics

logger = logging.getLogger(__name__)

ReadinessCheck = Callable[[], tuple[bool, dict[str, str]]]


class WorkerHealthServer:
    """`readiness_check` returns `(is_ready, {dependency_name: status})`."""

    def __init__(
        self,
        *,
        port: int,
        service_name: str,
        readiness_check: ReadinessCheck,
        metrics: WorkerMetrics,
        host: str = "0.0.0.0",  # noqa: S104 - intentional: bound inside a container network
    ) -> None:
        self._metrics = metrics
        handler = _make_handler(service_name, readiness_check, metrics)
        self._httpd = ThreadingHTTPServer((host, port), handler)
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name="worker-health", daemon=True
        )
        self._thread.start()
        logger.info("health server started", extra={"port": self._httpd.server_address[1]})

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)


def _make_handler(
    service_name: str, readiness_check: ReadinessCheck, metrics: WorkerMetrics
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass  # structured logging is handled by the worker itself, not stdlib access logs

        def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
            if self.path == "/health":
                self._respond(200, "text/plain", f"{service_name} alive\n")
            elif self.path == "/ready":
                is_ready, details = readiness_check()
                body = "\n".join(f"{k}: {v}" for k, v in details.items()) + "\n"
                self._respond(200 if is_ready else 503, "text/plain", body)
            elif self.path == "/metrics":
                self._respond(200, "text/plain; version=0.0.4", metrics.render_prometheus_text())
            else:
                self._respond(404, "text/plain", "not found\n")

        def _respond(self, status: int, content_type: str, body: str) -> None:
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return Handler
