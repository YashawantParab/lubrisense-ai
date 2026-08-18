"""Plain-object metrics + a hand-written Prometheus text exposition renderer.

No `prometheus_client` dependency — Phase 6 brief §37 only asked that metrics be
"accessible/loggable", with full observability deferred to Phase 26. Prometheus text
format is simple enough to render by hand, which gives a free upgrade path to real
scraping later without adding a dependency now.

Originally `app.pipeline.metrics.PipelineMetrics` (Phase 6) — relocated here in Phase 7
since the same generic counters/gauges object is reused by the data-quality worker, which
has nothing to do with telemetry ingestion specifically (TECHNICAL_DECISIONS.md, shared
worker infra ADR).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class WorkerMetrics:
    """Thread-safe counters. The MQTT bridge increments these from paho-mqtt's own
    network thread as well as the asyncio loop, so every mutation is lock-guarded."""

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)
    _counters: dict[str, int] = field(default_factory=dict, repr=False)
    _gauges: dict[str, float] = field(default_factory=dict, repr=False)

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + amount

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def snapshot(self) -> tuple[dict[str, int], dict[str, float]]:
        with self._lock:
            return dict(self._counters), dict(self._gauges)

    def render_prometheus_text(self) -> str:
        counters, gauges = self.snapshot()
        lines = [
            f"# TYPE {name} counter\n{name} {value}" for name, value in sorted(counters.items())
        ]
        lines += [f"# TYPE {name} gauge\n{name} {value}" for name, value in sorted(gauges.items())]
        return "\n".join(lines) + "\n"
