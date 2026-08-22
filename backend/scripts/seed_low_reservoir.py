"""Demo scenario — a low-reservoir supply-risk incident (docs/HOSTED_DEPLOYMENT.md "10
meaningful synthetic scenarios" pass). Seeds Crusher 005 (`L1-E915-M005`, the
`lubrisense-demo` tenant) with a reservoir level declining steadily down through the
`RESERVOIR_LEVEL_LOW` warning threshold (`demo_rules_policy.yaml`'s
`reservoir.low_level_warning_percent: 20.0`) but deliberately stopping well above the
critical threshold (`low_level_critical_percent: 8.0`) — a genuine "plan a refill soon"
supply-risk story, not a full outage. `RESERVOIR_LEVEL_LOW` is an engineering-limit-based
threshold check, not a baseline deviation (`check_reservoir_level_low` in
`app.rules_engine.rules.single_signal`), and its debounce is 2 consecutive reprocess
cycles, not the usual 3 (`demo_rules_policy.yaml`'s `debounce.by_finding_type`). Everything
else (pressure, pump current, bearing/vibration) stays flat/normal — this is a supply
story, not a restriction or bearing story. Drives the real telemetry -> rule-finding ->
condition -> decision -> incident chain and leaves the incident ACKNOWLEDGED.

    uv run python scripts/seed_low_reservoir.py

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
from app.domain.models import Sensor
from app.incidents.services.incident_service import IncidentService
from app.infrastructure.database import Database
from app.repositories.telemetry import TelemetryRepository
from app.rules_engine.workers.reprocess import reprocess
from scripts._scenario_seed_common import (
    advance_incident_to,
    envelope,
    mark_sensor_quality,
    reset_machine_data,
    resolve_machine,
)

ASSET_CODE = "L1-E915-M005"
DEVICE_ID = "low-reservoir-seed"


async def main() -> None:
    settings = get_settings()
    database = Database(settings)
    now = datetime.now(UTC)
    healthy_start = now - timedelta(hours=4)
    decline_start = now - timedelta(hours=2)

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

        rng = random.Random(20260821103)

        def jitter(value: float, magnitude: float) -> float:
            return value + rng.uniform(-magnitude, magnitude)

        # Two DISTINCT depletion rates, matching `seed_flagship_story.py`'s own proven
        # reservoir technique — NOT a single constant rate. `reprocess(tenant_id,
        # machine_id, decline_start, now)` scopes its "recent" window to exactly the
        # decline phase, compared against the baseline built from exactly the healthy
        # phase (`backfill(healthy_start, decline_start)`); `RESERVOIR_DEPLETION_ABNORMAL`
        # only fires when the recent rate exceeds the baseline rate. An earlier version of
        # this script used one constant rate across both phases, intending "no rate
        # change, so no leakage signal" — but a baseline built from a perfectly consistent
        # linear rate has a near-zero MAD, so even trivial noise-driven differences between
        # the two windows' *measured* rates occasionally read as a huge standardized
        # deviation and spuriously fire `RESERVOIR_DEPLETION_ABNORMAL` alongside
        # `RESERVOIR_LEVEL_LOW`, producing `AMBIGUOUS_CONDITION` instead of the intended
        # single-cause `LOW_LUBRICANT_AVAILABILITY` (found empirically re-running this
        # script). A decline-phase rate that is DISTINCTLY (not marginally) slower than the
        # healthy-phase rate keeps the recent/baseline ratio safely under the
        # `depletion_rate_abnormal_multiplier: 1.75` threshold regardless of noise.
        HEALTHY_LEVEL = 48.0
        MID_LEVEL = 22.0
        FINAL_LEVEL = 15.0
        _healthy_minutes = (decline_start - healthy_start).total_seconds() / 60.0
        _decline_minutes = (now - decline_start).total_seconds() / 60.0
        HEALTHY_RATE_PCT_PER_MIN = (HEALTHY_LEVEL - MID_LEVEL) / _healthy_minutes
        DECLINE_RATE_PCT_PER_MIN = (MID_LEVEL - FINAL_LEVEL) / _decline_minutes

        def reservoir_value(t: datetime) -> float:
            if t <= decline_start:
                minutes = (t - healthy_start).total_seconds() / 60.0
                return HEALTHY_LEVEL - HEALTHY_RATE_PCT_PER_MIN * minutes
            minutes_after = (t - decline_start).total_seconds() / 60.0
            return MID_LEVEL - DECLINE_RATE_PCT_PER_MIN * minutes_after

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

        # --- 1. Healthy period (4h -> 2h ago): calm baseline, normal consumption.
        steps = 120
        for i in range(steps):
            t = healthy_start + (decline_start - healthy_start) * (i / steps)
            add(pressure, jitter(9.0, 0.15), t, circuit=circuit_id)
            add(pump_current, jitter(3.0, 0.05), t)
            add(reservoir, jitter(reservoir_value(t), 0.1), t)
            add(rpm, jitter(1450.0, 3.0), t)
            for b in bearing_temps:
                add(b, jitter(41.0, 0.15), t)
            for v in vibrations:
                add(v, jitter(2.0, 0.03), t)

        # --- 2. Decline (2h ago -> now): reservoir drains down through the warning band.
        steps = 60
        for i in range(steps):
            frac = (i + 1) / steps
            t = decline_start + (now - decline_start) * frac
            add(pressure, jitter(9.0, 0.15), t, circuit=circuit_id)
            add(pump_current, jitter(3.0, 0.05), t)
            add(reservoir, jitter(reservoir_value(t), 0.1), t)
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
        await backfill(tenant_id, sid, healthy_start, decline_start)
        await backfill(tenant_id, sid, healthy_start, decline_start)
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

    # RESERVOIR_LEVEL_LOW debounce is 2, not the usual 3 (demo_rules_policy.yaml).
    for _ in range(2):
        await reprocess(tenant_id, machine_id, decline_start, now)
    print("Reprocessed rules over the decline window")

    # Deliberately no `LUBRICATION_DELIVERY_STATE` replay here (unlike the other scenario
    # scripts) — found empirically that a state-estimate vote on this machine's reservoir
    # trend reads as a second, competing hypothesis alongside the rule-based
    # `RESERVOIR_LEVEL_LOW` -> `LOW_LUBRICANT_AVAILABILITY` evidence, producing
    # `AMBIGUOUS_CONDITION` instead of this scenario's intended single-cause story. The
    # condition/decision/incident chain works correctly from rule evidence alone, which is
    # the only evidence this specific scenario needs.

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
    print(f"Low reservoir story complete: machine_id={machine_id} incident_id={incident.id}")
    print(f"View at: http://localhost:3000/machines/{machine_id}")


if __name__ == "__main__":
    asyncio.run(main())
