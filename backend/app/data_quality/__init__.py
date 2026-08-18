"""Phase 7 data-quality engine: structured, versioned assessment of telemetry before
baselines/rules/ML/Kalman/condition intelligence (Phase 8+) ever consume it.

Runs as a separate worker process (`python -m app.data_quality.worker`), consuming the
same Kafka telemetry topic the Phase 6 `telemetry-consumer` reads, on its own consumer
group — quality-worker failure/lag never blocks or slows telemetry ingestion (see
TECHNICAL_DECISIONS.md, quality-worker-architecture ADR).
"""

from __future__ import annotations
