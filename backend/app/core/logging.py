"""Structured logging foundation.

Emits one JSON object per log line with timestamp, level, service, message, and
correlation_id (when available in the current request context). `LOG_FORMAT=console` switches
to a human-readable formatter for local development.

This is intentionally a thin stdlib-`logging` setup rather than a tracing framework — Phase 1
only needs machine-readable logs. OpenTelemetry instrumentation is a later-phase addition and
should plug into this same `correlation_id` field as `trace_id`/`span_id` become available.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from app.core.context import get_correlation_id


class JSONLogFormatter(logging.Formatter):
    def __init__(self, *, service_name: str = "lubrisense-backend") -> None:
        super().__init__()
        self._service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "service": self._service_name,
            "message": record.getMessage(),
            "logger": record.name,
        }
        correlation_id = get_correlation_id()
        if correlation_id:
            payload["correlation_id"] = correlation_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


class ConsoleLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        correlation_id = get_correlation_id() or "-"
        base = (
            f"{self.formatTime(record, '%Y-%m-%d %H:%M:%S')} "
            f"[{record.levelname:<8}] {record.name} "
            f"(correlation_id={correlation_id}): {record.getMessage()}"
        )
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def configure_logging(
    *, level: str, log_format: str, service_name: str = "lubrisense-backend"
) -> None:
    formatter: logging.Formatter = (
        JSONLogFormatter(service_name=service_name)
        if log_format == "json"
        else ConsoleLogFormatter()
    )

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level.upper())

    # Quiet noisy libraries down to their own explicit level rather than inheriting DEBUG.
    for noisy_logger in ("uvicorn.access", "uvicorn.error"):
        logging.getLogger(noisy_logger).setLevel(level.upper())
