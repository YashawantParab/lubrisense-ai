"""Demo scenario — a possible-leakage incident (docs/HOSTED_DEPLOYMENT.md "10 meaningful
synthetic scenarios" pass). Seeds Pump 009 (`L1-07A8-M009`, the `lubrisense-demo` tenant)
with a healthy period followed by reservoir depletion at a materially faster rate than its
own healthy-window baseline rate, while pressure/flow-adjacent evidence stays normal — the
`RESERVOIR_DEPLETION_ABNORMAL` single-signal finding (`POSSIBLE_LEAKAGE_PATTERN`), not the
cross-signal `FLOW_PRESSURE_LEAKAGE_PATTERN` pattern (this topology has no FLOW sensor, so
that pattern can never fire — same reasoning `seed_flagship_story.py` documents for
restriction). Drives the real telemetry -> baseline -> rule-finding -> condition ->
decision -> incident chain and leaves the incident ACKNOWLEDGED — an active/acknowledged
issue, no maintenance case yet.

Pressure is kept flat/normal so this reads as leakage, not restriction: a genuine
depletion-rate change, not just noise (`check_reservoir_depletion_abnormal` requires the
*rate* to exceed the baseline rate by the same mild/strong MAD multiplier every other
single-signal rule uses).

    uv run python scripts/seed_leakage.py

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

ASSET_CODE = "L1-07A8-M009"
DEVICE_ID = "leakage-seed"


async def main() -> None:
    settings = get_settings()
    database = Database(settings)
    now = datetime.now(UTC)
    healthy_start = now - timedelta(hours=3)
    leak_start = now - timedelta(hours=1)

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

        rng = random.Random(20260821102)

        def jitter(value: float, magnitude: float) -> float:
            return value + rng.uniform(-magnitude, magnitude)

        # Healthy depletion rate: slow, steady. Leak-phase rate is set well past
        # `demo_rules_policy.yaml`'s `reservoir.depletion_rate_abnormal_multiplier: 1.75`
        # (>3x here) so the classifier's standardized distance clears the STRONG threshold
        # comfortably even with jitter noise.
        HEALTHY_RATE_PCT_PER_MIN = 0.03
        LEAK_RATE_PCT_PER_MIN = 0.12
        _leak_anchor = 62.0 - HEALTHY_RATE_PCT_PER_MIN * (
            (leak_start - healthy_start).total_seconds() / 60.0
        )

        def reservoir_value(t: datetime) -> float:
            if t <= leak_start:
                minutes = (t - healthy_start).total_seconds() / 60.0
                return 62.0 - HEALTHY_RATE_PCT_PER_MIN * minutes
            minutes_after = (t - leak_start).total_seconds() / 60.0
            return _leak_anchor - LEAK_RATE_PCT_PER_MIN * minutes_after

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

        # --- 1. Healthy period (3h -> 1h ago): calm baseline, slow reservoir depletion.
        steps = 130
        for i in range(steps):
            t = healthy_start + (leak_start - healthy_start) * (i / steps)
            add(pressure, jitter(9.0, 0.15), t, circuit=circuit_id)
            add(pump_current, jitter(3.0, 0.05), t)
            add(reservoir, reservoir_value(t), t)
            add(rpm, jitter(1450.0, 3.0), t)
            for b in bearing_temps:
                add(b, jitter(41.0, 0.15), t)
            for v in vibrations:
                add(v, jitter(2.0, 0.03), t)

        # --- 2. Leak developing (1h ago -> now): reservoir drains materially faster;
        # pressure/pump current stay flat — this is a delivery-supply story, not a
        # restriction story.
        steps = 40
        for i in range(steps):
            frac = (i + 1) / steps
            t = leak_start + (now - leak_start) * frac
            add(pressure, jitter(9.0, 0.15), t, circuit=circuit_id)
            add(pump_current, jitter(3.0, 0.05), t)
            add(reservoir, reservoir_value(t), t)
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
        await backfill(tenant_id, sid, healthy_start, leak_start)
        await backfill(tenant_id, sid, healthy_start, leak_start)
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

    # RESERVOIR window is 6h (demo_rules_policy.yaml window_minutes.by_category.RESERVOIR)
    # so the reprocess window must span back far enough to include the healthy anchor the
    # depletion-rate comparison needs.
    for _ in range(3):
        await reprocess(tenant_id, machine_id, healthy_start, now)
    print("Reprocessed rules over the full healthy+leak window")

    try:
        ticks = await replay_state_estimates(
            database,
            tenant_id,
            machine_id,
            "LUBRICATION_DELIVERY_STATE",
            tuple(healthy_start + (now - healthy_start) * f for f in (0.0, 0.5, 0.75, 0.9, 1.0)),
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
            incidents, tenant_id, incident, IncidentState.ACKNOWLEDGED
        )
        await session.commit()
        print(f"Incident state: {incident.state.value} (left acknowledged — no maintenance case)")

    await database.dispose()
    print("")
    print(f"Leakage story complete: machine_id={machine_id} incident_id={incident.id}")
    print(f"View at: http://localhost:3000/machines/{machine_id}")


if __name__ == "__main__":
    asyncio.run(main())
