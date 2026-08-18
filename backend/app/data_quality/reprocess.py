"""Historical reprocessing CLI (Phase 7 brief §31):

    python -m app.data_quality.reprocess --tenant-id ... --sensor-id ... \\
        --start 2026-08-01T00:00:00 --end 2026-08-01T06:00:00

Re-runs event-level rules over a historical range under the CURRENT policy — reading
already-persisted `Telemetry` rows directly rather than replaying Kafka, since everything
`QualityEngine.process_event` needs (asset context, sensor identity) is already denormalized
onto the telemetry row from the original enrichment. Idempotent: event-scoped issues are
`ON CONFLICT DO NOTHING` keyed on `rule_version` (`QualityIssueRepository.create_event_issue`),
so re-running under an unchanged `rule_version` is a safe no-op; a `rule_version` bump writes
new versioned rows without touching or deleting the prior ones — provenance preserved.

Known limitation: event-level rules that consult `SensorContext` (sequence gap, out-of-order,
spike) read the sensor's *current* live `SensorQualityState`, not its state as of the start
of the historical window being reprocessed — a live sensor kept reporting after the
reprocessed window closed, so "the previous reading" for context purposes is whichever event
was last processed for real, not whichever came right before the reprocessed range
chronologically. Acceptable for this reference implementation (the primary reprocessing use
case is re-scoring against an updated `rule_version`/policy, not exact historical replay of
context-dependent state) — see docs/DATA_QUALITY.md.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from datetime import datetime

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.data_quality.config.policy import load_quality_policy
from app.data_quality.services.quality_engine import QualityEngine
from app.domain.models import Telemetry
from app.infrastructure.database import Database
from app.pipeline.enrichment import EnrichedContext
from app.pipeline.validation import ValidatedTelemetry
from app.repositories.sensor import SensorRepository
from app.repositories.telemetry import TelemetryRepository


def _to_validated_telemetry(row: Telemetry) -> ValidatedTelemetry:
    assert row.machine_id is not None  # noqa: S101 - only reprocessable rows are passed in
    return ValidatedTelemetry(
        event_id=row.event_id,
        schema_version=row.schema_version,
        correlation_id=row.correlation_id,
        tenant_id=row.tenant_id,
        site_id=row.site_id,
        plant_id=row.plant_id,
        line_id=row.production_line_id,
        machine_id=row.machine_id,
        bearing_id=row.bearing_id,
        lubrication_system_id=row.lubrication_system_id,
        circuit_id=row.circuit_id,
        lubrication_point_id=row.lubrication_point_id,
        component_id=None,
        sensor_id=row.sensor_id,
        measurement_type=row.measurement_type.value,
        value=row.value,
        unit=row.unit,
        quality=row.quality.value,
        operating_state=row.operating_state,
        source_timestamp=row.source_timestamp,
        edge_received_timestamp=row.edge_received_timestamp,
        edge_emitted_timestamp=row.edge_emitted_timestamp,
        sequence_number=row.sequence_number,
        gateway_id=row.gateway_id,
        device_id=row.device_id,
        firmware_version=row.firmware_version,
        controller_version=row.controller_version,
        source=row.source,
        metadata=row.metadata_,
    )


def _to_enriched_context(row: Telemetry) -> EnrichedContext:
    assert row.machine_id is not None  # noqa: S101 - only reprocessable rows are passed in
    return EnrichedContext(
        site_id=row.site_id,
        plant_id=row.plant_id,
        production_line_id=row.production_line_id,
        machine_id=row.machine_id,
        bearing_id=row.bearing_id,
        lubrication_system_id=row.lubrication_system_id,
        circuit_id=row.circuit_id,
        lubrication_point_id=row.lubrication_point_id,
    )


async def reprocess(
    tenant_id: uuid.UUID, sensor_id: uuid.UUID, start: datetime, end: datetime
) -> int:
    settings = get_settings()
    policy = load_quality_policy()
    database = Database(settings)
    processed = 0
    try:
        async with database.session() as session:
            telemetry_repo = TelemetryRepository(session)
            sensor_repo = SensorRepository(session)
            engine = QualityEngine(session, policy)

            sensor = await sensor_repo.get(tenant_id, sensor_id)
            if sensor is None:
                raise SystemExit(f"sensor {sensor_id} not found for tenant {tenant_id}")

            rows = await telemetry_repo.get_by_sensor_time_range(
                tenant_id, sensor_id, start=start, end=end, limit=2000
            )
            # Oldest-first: rules consult "what was seen just before this event", so replay
            # must follow event-time order even though the repository query returns DESC.
            for row in sorted(rows, key=lambda r: r.source_timestamp):
                if row.machine_id is None:
                    continue
                event = _to_validated_telemetry(row)
                enriched = _to_enriched_context(row)
                async with session.begin_nested():
                    await engine.process_event(event, enriched, sensor, row.mqtt_received_timestamp)
                processed += 1
            await session.commit()
    finally:
        await database.dispose()
    return processed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reprocess historical telemetry through the current data-quality policy."
    )
    parser.add_argument("--tenant-id", required=True, type=uuid.UUID)
    parser.add_argument("--sensor-id", required=True, type=uuid.UUID)
    parser.add_argument("--start", required=True, type=datetime.fromisoformat)
    parser.add_argument("--end", required=True, type=datetime.fromisoformat)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        log_format=settings.log_format,
        service_name="lubrisense-data-quality-reprocess",
    )
    count = asyncio.run(reprocess(args.tenant_id, args.sensor_id, args.start, args.end))
    print(f"reprocessed {count} events for sensor {args.sensor_id}")  # noqa: T201 - CLI output


if __name__ == "__main__":
    main()
