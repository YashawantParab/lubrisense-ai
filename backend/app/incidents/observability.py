"""Process-local metrics for the incidents package (Phase 16 brief). No periodic worker —
incidents are only ever (re)evaluated on-demand via `IncidentService.evaluate_machine()`,
same on-demand precedent as Phase 11-15 (ADR-100/109/124)."""

from __future__ import annotations

from app.observability.metrics import WorkerMetrics

METRICS = WorkerMetrics()
