"""Process-local metrics for the prognostics package (Phase 15 brief). Mirrors
`app.condition_intelligence.observability` / `app.state_estimation.observability` — no
periodic worker, so metrics are exposed through this package's own
`/api/v1/prognostics/metrics` route."""

from __future__ import annotations

from app.observability.metrics import WorkerMetrics

METRICS = WorkerMetrics()
