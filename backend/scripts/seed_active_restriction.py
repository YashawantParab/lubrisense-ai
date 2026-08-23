"""Demo scenario — an ACTIVE developing-restriction incident (docs/HOSTED_DEPLOYMENT.md
"10 meaningful synthetic scenarios" pass). Seeds Stacker-Reclaimer SR-201 (`L2-07A8-M012`, the same
`lubrisense-demo` tenant as the flagship/healthy machines) with a healthy period followed
by a steadily rising main-line pressure trend, drives it through the real
telemetry -> baseline -> rule-finding -> condition -> decision -> incident chain, and
leaves the incident OPEN/INVESTIGATING — deliberately never resolved, unlike the flagship
story. This is the "active attention case" showcase item: elevated pressure trend,
recommended inspection, no maintenance case created yet.

Single-signal evidence only (`PRESSURE_ABOVE_CONTEXTUAL_BASELINE` ->
`DEVELOPING_RESTRICTION_PATTERN`) — this topology has no FLOW sensor, so the cross-signal
`FLOW_PRESSURE_RESTRICTION_PATTERN` pattern can never fire here (same reasoning
`seed_flagship_story.py` documents). Pump current and bearing/vibration are kept flat: no
secondary bearing effect in this story, and a co-active `PUMP_CURRENT_ABOVE_BASELINE`
would vote a second hypothesis into `AMBIGUOUS_CONDITION` (ADR-172).

    uv run python scripts/seed_active_restriction.py

Safe to re-run: deletes and rebuilds only this one machine's own telemetry/state
estimates first (ADR-173), and `IncidentService`'s correlation-key dedup means a second
run re-evaluates the same open incident in place rather than creating a duplicate.
"""

from __future__ import annotations

import asyncio
import random
import uuid
from datetime import UTC, datetime, timedelta

from app.baselines.workers.backfill import backfill
from app.core.config import get_settings
from app.domain.enums import Eligibility, IncidentState, QualityState
from app.domain.models import Sensor
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

ASSET_CODE = "L2-07A8-M012"
DEVICE_ID = "active-restriction-seed"


async def main() -> None:
    settings = get_settings()
    database = Database(settings)
    now = datetime.now(UTC)
    healthy_start = now - timedelta(hours=3)
    restriction_start = now - timedelta(minutes=40)

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

        rng = random.Random(20260821101)

        def jitter(value: float, magnitude: float) -> float:
            return value + rng.uniform(-magnitude, magnitude)

        rows: list[dict[str, object]] = []

        def add(
            sensor: Sensor, value: float, t: datetime, *, circuit: uuid.UUID | None = None
        ) -> None:
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
            t = healthy_start + (restriction_start - healthy_start) * (i / steps)
            add(pressure, jitter(9.0, 0.15), t, circuit=circuit_id)
            add(pump_current, jitter(3.0, 0.05), t)
            add(reservoir, jitter(58.0 - 0.01 * i, 0.05), t)
            add(rpm, jitter(1450.0, 3.0), t)
            for b in bearing_temps:
                add(b, jitter(41.0, 0.15), t)
            for v in vibrations:
                add(v, jitter(2.0, 0.03), t)

        # --- 2. Developing restriction (40min ago -> now): pressure climbs steadily to a
        # STRONG deviation (>4x MAD, demo_rules_policy.yaml's `deviation.strong_multiplier`)
        # so the incident fires reliably. Everything else stays flat/normal — a still-active,
        # single-cause story, not a compound one.
        steps = 24
        for i in range(steps):
            frac = (i + 1) / steps
            t = restriction_start + (now - restriction_start) * frac
            add(pressure, jitter(9.0 + 16.0 * frac, 0.15), t, circuit=circuit_id)
            add(pump_current, jitter(3.0, 0.05), t)
            add(reservoir, jitter(56.5 - 0.01 * i, 0.05), t)
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
            last_observed_at=now,
        )
    print(f"Marked {len(all_sensor_ids)} sensors ELIGIBLE")

    for sid in all_sensor_ids:
        await backfill(tenant_id, sid, healthy_start, restriction_start)
        await backfill(tenant_id, sid, healthy_start, restriction_start)
    print("Built baselines from the healthy window")

    for sid in all_sensor_ids:
        await mark_sensor_quality(
            database,
            tenant_id,
            machine_id,
            sid,
            quality_state=QualityState.TRUSTED,
            eligibility=Eligibility.ELIGIBLE,
            last_observed_at=now,
        )

    for _ in range(3):
        await reprocess(tenant_id, machine_id, restriction_start, now)
    print("Reprocessed rules over the restriction window")

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
        print(f"Incident state: {incident.state.value} (left open — no maintenance case)")

    await database.dispose()
    print("")
    print(f"Active restriction story complete: machine_id={machine_id} incident_id={incident.id}")
    print(f"View at: http://localhost:3000/machines/{machine_id}")


if __name__ == "__main__":
    asyncio.run(main())
