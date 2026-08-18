"""Request-scoped context propagated through logging and responses.

Kept minimal in Phase 1: a single correlation ID. This is the seam distributed tracing
(OpenTelemetry trace/span IDs) will extend later without changing call sites that already
depend on `get_correlation_id()`.
"""

from __future__ import annotations

from contextvars import ContextVar

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def set_correlation_id(correlation_id: str) -> None:
    _correlation_id.set(correlation_id)


def get_correlation_id() -> str | None:
    return _correlation_id.get()
