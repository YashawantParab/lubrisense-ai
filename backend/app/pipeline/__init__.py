"""Phase 6 central telemetry pipeline: MQTT ingestion -> Kafka -> Timescale persistence.

Runs as separate long-running worker processes (`python -m app.pipeline.mqtt_bridge`,
`python -m app.pipeline.consumer`), not as FastAPI request handlers — see
TECHNICAL_DECISIONS.md ADR-050 and docs/TELEMETRY_PIPELINE.md.
"""

from __future__ import annotations
