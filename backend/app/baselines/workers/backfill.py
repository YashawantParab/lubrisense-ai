"""Historical baseline backfill CLI (Phase 8 brief §31/§45):

    python -m app.baselines.workers.backfill \\
        --tenant-id ... --sensor-id ... --start 2026-08-01T00:00:00 --end 2026-08-02T00:00:00

Runs `BaselineEngine.refresh_sensor` once against the exact given range (via
`window_override`) rather than "now minus the configured rolling window" — the same engine
method the live worker uses (brief §28), just with an explicit historical window. Never
deletes prior baseline versions (brief §31) — a backfill run participates in the same
promotion/stability-gate machinery as a live cycle, so it can only ever produce a new
version through the normal contamination-control path, not by overwriting history.

Without `--sensor-id`, backfills every sensor currently tracked in `sensor_quality_state`
for the tenant — the tool this repo's performance measurement (brief §45) is run with.
"""

from __future__ import annotations

import argparse
import asyncio
import time
import uuid
from datetime import datetime

from app.baselines.config.policy import load_baseline_policy
from app.baselines.services.baseline_engine import BaselineEngine
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.data_quality.repositories.sensor_quality_state_repository import (
    SensorQualityStateRepository,
)
from app.infrastructure.database import Database
from app.repositories.sensor import SensorRepository


async def backfill(
    tenant_id: uuid.UUID, sensor_id: uuid.UUID | None, start: datetime, end: datetime
) -> dict[str, int | float]:
    settings = get_settings()
    policy = load_baseline_policy()
    database = Database(settings)
    started = time.monotonic()
    sensors_processed = machines_processed = 0
    try:
        async with database.session() as session:
            sensor_repo = SensorRepository(session)
            quality_repo = SensorQualityStateRepository(session)
            engine = BaselineEngine(session, policy)

            # `SensorQualityState.machine_id` (Phase 7) is denormalized from the telemetry
            # envelope's own resolved `machine_id`, unlike `Sensor.machine_id` (Phase 2)
            # which is only set for a sensor attached *directly* to a machine — most
            # sensors attach to a circuit/reservoir/pump/bearing instead
            # (docs/ASSET_HIERARCHY.md), so this is the correct source for cycle-baseline
            # machine discovery, matching what `BaselineEngine.refresh_sensor` itself uses.
            machines_seen: set[uuid.UUID] = set()
            if sensor_id is not None:
                sensor = await sensor_repo.get(tenant_id, sensor_id)
                if sensor is None:
                    raise SystemExit(f"sensor {sensor_id} not found for tenant {tenant_id}")
                await engine.refresh_sensor(tenant_id, sensor, end, window_override=(start, end))
                sensors_processed += 1
                quality_state = await quality_repo.get(tenant_id, sensor_id)
                if quality_state is not None and quality_state.machine_id is not None:
                    machines_seen.add(quality_state.machine_id)
            else:
                tracked = await quality_repo.list_for_tenant(tenant_id, limit=2000)
                for row in tracked:
                    sensor = await sensor_repo.get(tenant_id, row.sensor_id)
                    if sensor is None:
                        continue
                    await engine.refresh_sensor(
                        tenant_id, sensor, end, window_override=(start, end)
                    )
                    sensors_processed += 1
                    if row.machine_id is not None:
                        machines_seen.add(row.machine_id)

            for machine_id in machines_seen:
                await engine.refresh_machine_cycle(
                    tenant_id, machine_id, end, window_override=(start, end)
                )
                machines_processed += 1

            await session.commit()
    finally:
        await database.dispose()

    return {
        "sensors_processed": sensors_processed,
        "machines_processed": machines_processed,
        "duration_seconds": time.monotonic() - started,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill baselines over historical telemetry.")
    parser.add_argument("--tenant-id", required=True, type=uuid.UUID)
    parser.add_argument("--sensor-id", required=False, type=uuid.UUID, default=None)
    parser.add_argument("--start", required=True, type=datetime.fromisoformat)
    parser.add_argument("--end", required=True, type=datetime.fromisoformat)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        log_format=settings.log_format,
        service_name="lubrisense-baseline-backfill",
    )
    result = asyncio.run(backfill(args.tenant_id, args.sensor_id, args.start, args.end))
    print(  # noqa: T201 - CLI output
        f"backfilled {result['sensors_processed']} sensor(s), "
        f"{result['machines_processed']} machine cycle profile(s) "
        f"in {result['duration_seconds']:.2f}s"
    )


if __name__ == "__main__":
    main()
