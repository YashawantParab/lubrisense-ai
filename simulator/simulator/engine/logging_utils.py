"""Structured simulator logging (Phase 3 brief §25).

Logs the *events* of a simulation run (start/stop, cycle start/complete, operating-state
transitions, invalid state) at INFO. Deliberately does not log every sensor reading — with
a 5s step across an hours-long run that would be an unusable volume of log output; use the
JSONL/CSV output files (`simulator.engine.output`) to inspect individual readings instead.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "event_data", None)
        if extra:
            payload.update(extra)
        return json.dumps(payload, default=str)


def get_simulator_logger(name: str = "simulator") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(JsonLogFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def log_event(logger: logging.Logger, event: str, message: str, **fields: Any) -> None:
    logger.info(message, extra={"event_data": {"event": event, **fields}})
