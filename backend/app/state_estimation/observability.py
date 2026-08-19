"""Process-local metrics for the state-estimation package (Phase 12 brief §34).

There is no periodic worker/container for Phase 12 (ADR: on-demand state estimation, no
periodic worker — mirrors ADR-100's ML precedent), so there is no per-worker health-server
port to expose these on the way Phase 6-10's workers do. Reuses the exact same
`app.observability.metrics.WorkerMetrics` renderer as those workers, exposed instead
through a small route on this package's own `/api/v1/state-estimation/metrics` (see
`app.api.v1.state_estimation`) — process-wide, not tenant-scoped, matching how `/health`/
`/ready` are also unscoped.
"""

from __future__ import annotations

from app.observability.metrics import WorkerMetrics

METRICS = WorkerMetrics()
