"""Demo scenario — a pump-performance-degradation incident (docs/HOSTED_DEPLOYMENT.md "10
meaningful synthetic scenarios" pass). Seeds Compressor 004 (`L2-7B43-M004`, the
`lubrisense-demo` tenant) with a healthy period followed by pump current climbing
materially above its own baseline while pressure stays flat/normal — the single-signal
`PUMP_CURRENT_ABOVE_BASELINE` finding (`PUMP_PERFORMANCE_DEGRADATION`), never the
cross-signal `PUMP_DEGRADATION_PATTERN` pattern (which requires `PRESSURE_BUILD_SLOW`, a
cycle-level rule this simple two-phase telemetry does not attempt to synthesize).
Pressure/reservoir/bearing all stay flat/normal: a co-active `PRESSURE_ABOVE_CONTEXTUAL_
BASELINE` finding would vote a second hypothesis into `AMBIGUOUS_CONDITION` instead of a
clean pump-degradation read (same reasoning `seed_flagship_story.py` documents for keeping
pump current flat during its own restriction story, mirrored here in the other direction).
Drives the real telemetry -> baseline -> rule-finding -> condition -> decision -> incident
chain and leaves the incident INVESTIGATING — "inspect pump performance."

    uv run python scripts/seed_pump_degradation.py

Safe to re-run: deletes and rebuilds only this one machine's own telemetry/state estimates
first (ADR-173); `IncidentService`'s correlation-key dedup and `advance_incident_to`'s
already-passed-transition guard make a second run a no-op past the first.
"""

from __future__ import annotations

import asyncio
import random
import uuid
from datetime import UTC, datetime, timedelta

from app.baselines.workers.backfill import backfill
from app.core.config import get_settings
from app.domain.enums import Eligibility, IncidentState, QualityState
from app.incidents.services.incident_service import IncidentService
from app.infrastructure.database import Database
from app.repositories.telemetry import TelemetryRepository
from app.rules_engine.workers.reprocess import reprocess
from scripts._scenario_seed_common import (
    advance_incident_to,
    envelope,
    mark_sensor_quality,
    replay_state_estimates,
    reset_machine_data,
    resolve_machine,
)

ASSET_CODE = "L2-7B43-M004"
DEVICE_ID = "pump-degradation-seed"


async def main() -> None:
    settings = get_settings()
    database = Database(settings)
    now = datetime.now(UTC)
    healthy_start = now - timedelta(hours=3)
    degradation_start = now - timedelta(minutes=40)

    async with database.session() as session:
        base = await resolve_machine(session, ASSET_CODE)
        tenant_id, machine_id, circuit_id = base.tenant_id, base.machine_id, base.circuit_id
        by_type = base.by_type

        pressure = by_type["PRESSURE"][0]
        pump_current = by_type["PUMP_CURRENT"][0]
        reservoir = by_type["RESERVOIR_LEVEL"][0]
        rpm = by_type["RPM"][0]
        bearing_temps = by_type["BEARING_TEMPERATURE"]
        vibrations = by_type["VIBRATION_RMS"]

        await reset_machine_data(session, tenant_id, machine_id)

        rng = random.Random(20260821104)

        def jitter(value: float, magnitude: float) -> float:
            return value + rng.uniform(-magnitude, magnitude)

        rows: list[dict[str, object]] = []

        def add(sensor, value: float, t: datetime, *, circuit: uuid.UUID | None = None) -> None:
            rows.append(
                envelope(
                    tenant_id=tenant_id,
                    machine_id=machine_id,
                    sensor=sensor,
                    value=value,
                    t=t,
                    now=now,
                    circuit_id=circuit,
                    device_id=DEVICE_ID,
                )
            )

        # --- 1. Healthy period (3h -> 40min ago): calm baseline across every channel.
        steps = 130
        for i in range(steps):
            t = healthy_start + (degradation_start - healthy_start) * (i / steps)
            add(pressure, jitter(9.0, 0.15), t, circuit=circuit_id)
            add(pump_current, jitter(3.0, 0.05), t)
            add(reservoir, jitter(57.0 - 0.01 * i, 0.05), t)
            add(rpm, jitter(1450.0, 3.0), t)
            for b in bearing_temps:
                add(b, jitter(41.0, 0.15), t)
            for v in vibrations:
                add(v, jitter(2.0, 0.03), t)

        # --- 2. Pump degradation (40min ago -> now): pump current climbs steadily toward a
        # STRONG deviation while pressure/reservoir/bearing stay flat/normal.
        steps = 24
        for i in range(steps):
            frac = (i + 1) / steps
            t = degradation_start + (now - degradation_start) * frac
            add(pressure, jitter(9.0, 0.15), t, circuit=circuit_id)
            add(pump_current, jitter(3.0 + 2.6 * frac, 0.05), t)
            add(reservoir, jitter(55.6 - 0.01 * i, 0.05), t)
            add(rpm, jitter(1450.0, 3.0), t)
            for b in bearing_temps:
                add(b, jitter(41.0, 0.15), t)
            for v in vibrations:
                add(v, jitter(2.0, 0.03), t)

        repo = TelemetryRepository(session)
        await repo.batch_insert_idempotent(rows)
        await session.commit()
        print(f"Seeded {len(rows)} telemetry rows for machine={machine_id}")

        all_sensor_ids = [pressure.id, pump_current.id, reservoir.id, rpm.id]
        all_sensor_ids += [b.id for b in bearing_temps]
        all_sensor_ids += [v.id for v in vibrations]

    for sid in all_sensor_ids:
        await mark_sensor_quality(
            database,
            tenant_id,
            machine_id,
            sid,
            quality_state=QualityState.TRUSTED,
            eligibility=Eligibility.ELIGIBLE,
        )
    print(f"Marked {len(all_sensor_ids)} sensors ELIGIBLE")

    for sid in all_sensor_ids:
        await backfill(tenant_id, sid, healthy_start, degradation_start)
        await backfill(tenant_id, sid, healthy_start, degradation_start)
    print("Built baselines from the healthy window")

    for sid in all_sensor_ids:
        await mark_sensor_quality(
            database,
            tenant_id,
            machine_id,
            sid,
            quality_state=QualityState.TRUSTED,
            eligibility=Eligibility.ELIGIBLE,
        )

    for _ in range(3):
        await reprocess(tenant_id, machine_id, degradation_start, now)
    print("Reprocessed rules over the degradation window")

    try:
        ticks = await replay_state_estimates(
            database,
            tenant_id,
            machine_id,
            "LUBRICATION_DELIVERY_STATE",
            tuple(
                healthy_start + (now - healthy_start) * f for f in (0.0, 0.6, 0.85, 0.92, 0.97, 1.0)
            ),
        )
        print(f"Computed {ticks} LUBRICATION_DELIVERY_STATE ticks")
    except Exception as exc:  # noqa: BLE001 - best-effort for this demo story
        print(
            f"State estimation skipped ({exc}) — condition/decision still work "
            "from rule evidence alone"
        )

    async with database.session() as session:
        incidents = IncidentService(session)
        incident = await incidents.evaluate_machine(tenant_id, machine_id)
        await session.commit()
        if incident is None:
            print("No incident created — condition evidence did not warrant one this run")
            await database.dispose()
            return
        print(
            f"Incident: {incident.id} ({incident.incident_type.value}, {incident.severity.value})"
        )

        incident = await advance_incident_to(
            incidents, tenant_id, incident, IncidentState.INVESTIGATING
        )
        await session.commit()
        print(f"Incident state: {incident.state.value} (left investigating — no maintenance case)")

    await database.dispose()
    print("")
    print(f"Pump degradation story complete: machine_id={machine_id} incident_id={incident.id}")
    print(f"View at: http://localhost:3000/machines/{machine_id}")


if __name__ == "__main__":
    asyncio.run(main())
