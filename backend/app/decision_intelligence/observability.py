"""Process-local metrics for the decision-intelligence package (Phase 14 brief). Mirrors
`app.condition_intelligence.observability` / `app.prognostics.observability` — no periodic
worker, so metrics are exposed through this package's own `/api/v1/decisions/metrics`
route."""

from __future__ import annotations

from app.observability.metrics import WorkerMetrics

METRICS = WorkerMetrics()
