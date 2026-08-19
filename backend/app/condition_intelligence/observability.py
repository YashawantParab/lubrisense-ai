"""Process-local metrics for the condition-intelligence package (Phase 13 brief). There is
no periodic worker for Phase 13 (assessment is computed on-demand from a query, same
precedent as Phase 12's `app.state_estimation.observability`), so metrics are exposed
through this package's own `/api/v1/conditions/metrics` route rather than a dedicated
worker health port."""

from __future__ import annotations

from app.observability.metrics import WorkerMetrics

METRICS = WorkerMetrics()
