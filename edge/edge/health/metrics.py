"""`EdgeMetrics` — in-memory counters, reset only on process restart (Phase 5 brief §24).
Not a Prometheus/observability-platform integration — a lightweight foundation only."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class EdgeMetrics:
    acquired: int = 0
    buffered: int = 0
    sent: int = 0
    replayed: int = 0
    failures: int = 0
    duplicates_prevented: int = 0
    warnings: int = 0
    buffer_overflow_count: int = 0
    config_changes: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "acquired": self.acquired,
            "buffered": self.buffered,
            "sent": self.sent,
            "replayed": self.replayed,
            "failures": self.failures,
            "duplicates_prevented": self.duplicates_prevented,
            "warnings": self.warnings,
            "buffer_overflow_count": self.buffer_overflow_count,
            "config_changes": self.config_changes,
        }
