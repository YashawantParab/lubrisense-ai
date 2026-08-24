"""Demo scenario — a recently maintained, still-recovering asset (docs/HOSTED_DEPLOYMENT.md
"10 meaningful synthetic scenarios" pass). Seeds Bucket Elevator BE-201 (`L1-7F84-M016`,
the
`lubrisense-demo` tenant) with a shorter/milder developing-restriction than the flagship
story, a real maintenance action taken against it, and a PARTIAL recovery telemetry phase
(pressure declining but deliberately not fully back to its healthy baseline) — a different
story beat than the flagship's fully-closed-loop, fully-confirmed-normal ending
(`seed_flagship_story.py`). `MaintenanceService.complete()` performs a real, fresh
post-action `ConditionEngine.assess()` (see its own docstring) — because the recovery
telemetry is only partial, that fresh assessment is expected to land on the same
`DEVELOPING_RESTRICTION_PATTERN` condition type at a lower severity than the pre-action
assessment, which `app.condition_intelligence.services.lifecycle.classify_lifecycle`
classifies as `IMPROVING` (same condition_type as the immediately preceding assessment,
lower severity). If the recovery telemetry happens to read low enough to clear the finding
entirely instead, the fresh assessment lands on `NORMAL_OPERATION` and lifecycle reads
`RESOLVED` — still a legitimate "just recovered" story, so this script does not force one
outcome over the other.

    uv run python scripts/seed_recovering_asset.py

Safe to re-run: deletes and rebuilds only this one machine's own telemetry/state estimates
first (ADR-173); `IncidentService`'s correlation-key dedup and `advance_incident_to`'s
already-passed-transition guard make the incident/investigation steps a no-op on a second
run. The maintenance case re-runs `create_case_for_incident`/`plan`/`start` against the same
(already-correlated) incident each time — `MaintenanceService`'s own state-transition checks
make a second `start()`/`complete()` on an already-completed case a no-op-safe skip rather
than a duplicate case, mirroring `seed_flagship_story.py`'s own re-run story.
"""

from __future__ import annotations

import asyncio
import random
import uuid
from datetime import UTC, datetime, timedelta

from app.baselines.workers.backfill import backfill
from app.core.config import get_settings
from app.domain.enums import (
    Eligibility,
    FeedbackClassification,
    IncidentState,
    MaintenanceActionType,
    MaintenanceState,
    QualityState,
    TechnicianFindingResult,
)
from app.domain.models import Sensor
from app.incidents.services.incident_service import IncidentService
from app.infrastructure.database import Database
from app.maintenance.services.maintenance_service import MaintenanceService
from app.repositories.telemetry import TelemetryRepository
from app.rules_engine.workers.reprocess import reprocess
from scripts._scenario_seed_common import (
    advance_incident_to,
    envelope,
    mark_sensor_quality,
    reset_machine_data,
    resolve_machine,
)

ASSET_CODE = "L1-7F84-M016"
DEVICE_ID = "recovering-asset-seed"


async def main() -> None:
    settings = get_settings()
    database = Database(settings)
    now = datetime.now(UTC)
    healthy_start = now - timedelta(hours=3)
    restriction_start = now - timedelta(minutes=50)

    # One RNG and one continuous reservoir formula for the WHOLE script (healthy,
    # restriction, and recovery phases alike) — never a flat value with independently
    # -seeded jitter per phase. A perfectly flat reservoir split across separately-seeded
    # jitter streams gives a baseline MAD near zero, which makes
    # `RESERVOIR_DEPLETION_ABNORMAL`'s standardized-distance classifier blow up on pure
    # noise and vote a second, unrelated `POSSIBLE_LEAKAGE_PATTERN` hypothesis alongside
    # the real restriction one — exactly the sentinel-MAD bug `seed_flagship_story.py`'s
    # own reservoir comment describes. A single continuous rate (and one unbroken RNG
    # stream) keeps the recent-window rate equal to the baseline rate throughout, so this
    # stays a one-cause restriction/recovery story.
    rng = random.Random(20260821107)

    def jitter(value: float, magnitude: float) -> float:
        return value + rng.uniform(-magnitude, magnitude)

    # Matches `seed_flagship_story.py`'s own two-rate technique exactly: the post-healthy
    # segment depletes at a distinctly SLOWER rate than the healthy segment, never merely
    # an equal one — `RESERVOIR_DEPLETION_ABNORMAL` only fires when the recent rate
    # exceeds the baseline rate, so a slower recent rate is unconditionally safe even
    # against short-window sampling noise (an "equal" rate can still random-walk into
    # reading faster over a short recent window, which is what broke the first attempt at
    # this script).
    RESERVOIR_START = 55.0
    HEALTHY_RESERVOIR_RATE_PCT_PER_MIN = 0.02
    POST_HEALTHY_RESERVOIR_RATE_PCT_PER_MIN = 0.005
    _reservoir_anchor = RESERVOIR_START - HEALTHY_RESERVOIR_RATE_PCT_PER_MIN * (
        (restriction_start - healthy_start).total_seconds() / 60.0
    )

    def reservoir_value(t: datetime) -> float:
        if t <= restriction_start:
            minutes = (t - healthy_start).total_seconds() / 60.0
            return RESERVOIR_START - HEALTHY_RESERVOIR_RATE_PCT_PER_MIN * minutes
        minutes_after = (t - restriction_start).total_seconds() / 60.0
        return _reservoir_anchor - POST_HEALTHY_RESERVOIR_RATE_PCT_PER_MIN * minutes_after

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
        # Lubrication Efficiency Intelligence, Pass 1
        # (docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md, ADR-176) — BE-201 is this
        # capability's representative recovery case: a modest, delivery-linked rise
        # during the developing restriction (bearing_temps/vibrations stay flat in this
        # script's own design, so this is framed as general added mechanical resistance
        # from restricted delivery, never attributed to bearing friction specifically),
        # then a near-full return toward the healthy baseline after maintenance — mirrors
        # `pressure`'s own proportions below exactly, deliberately smaller in magnitude
        # than IDF-01's bearing-driven case.
        power = by_type["MACHINE_POWER"][0]

        await reset_machine_data(session, tenant_id, machine_id)

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

        # --- 1. Healthy period (3h -> 50min ago).
        steps = 120
        for i in range(steps):
            t = healthy_start + (restriction_start - healthy_start) * (i / steps)
            add(pressure, jitter(9.0, 0.15), t, circuit=circuit_id)
            add(pump_current, jitter(3.0, 0.05), t)
            add(reservoir, jitter(reservoir_value(t), 0.05), t)
            add(rpm, jitter(1450.0, 3.0), t)
            add(power, jitter(30.0, 0.6), t)
            for b in bearing_temps:
                add(b, jitter(41.0, 0.15), t)
            for v in vibrations:
                add(v, jitter(2.0, 0.03), t)

        # --- 2. Developing restriction (50min -> 25min ago): shorter and milder than the
        # flagship/active-restriction scripts' own rise — a genuinely smaller problem, not
        # a re-telling of the same story on a different machine.
        steps = 25
        for i in range(steps):
            frac = (i + 1) / steps
            t = restriction_start + (now - timedelta(minutes=25) - restriction_start) * frac
            add(pressure, jitter(9.0 + 8.0 * frac, 0.15), t, circuit=circuit_id)
            add(pump_current, jitter(3.0, 0.05), t)
            add(reservoir, jitter(reservoir_value(t), 0.05), t)
            add(rpm, jitter(1450.0, 3.0), t)
            add(power, jitter(30.0 + 4.0 * frac, 0.6), t)
            for b in bearing_temps:
                add(b, jitter(41.0, 0.15), t)
            for v in vibrations:
                add(v, jitter(2.0, 0.03), t)

        repo = TelemetryRepository(session)
        await repo.batch_insert_idempotent(rows)
        await session.commit()
        print(f"Seeded {len(rows)} pre-action telemetry rows for machine={machine_id}")

        all_sensor_ids = [pressure.id, pump_current.id, reservoir.id, rpm.id, power.id]
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
    print("Reprocessed rules over the pre-action window")

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

        maintenance = MaintenanceService(session)
        case = await maintenance.create_case_for_incident(tenant_id, incident.id)
        if case.state in (MaintenanceState.NOT_STARTED, MaintenanceState.REVIEW_REQUIRED):
            case = await maintenance.plan(tenant_id, case.id, planned_for=None)
        if case.state == MaintenanceState.PLANNED:
            case = await maintenance.start(tenant_id, case.id)
        await session.commit()
        print(f"Maintenance case: {case.id} ({case.recommended_action.value})")

        case = await maintenance.get(tenant_id, case.id)
        if case.state == MaintenanceState.IN_PROGRESS:
            await maintenance.record_finding(
                tenant_id,
                case.id,
                result=TechnicianFindingResult.PARTIALLY_CONFIRMED,
                component="distributor",
                observed_issue=(
                    "Elevated main-line pressure consistent with a developing, partial "
                    "restriction; cleared a partial blockage at the distributor outlet."
                ),
                notes="On-site inspection and partial clean-out performed.",
                technician_identifier="demo-technician",
            )
            await maintenance.record_action(
                tenant_id,
                case.id,
                action_type=MaintenanceActionType.CLEANED,
                notes=(
                    "Partially cleared distributor outlet; re-inspection "
                    "recommended to confirm full clearance."
                ),
                recorded_by="demo-technician",
            )
            await session.commit()

    # --- 3. Partial recovery telemetry (25min ago -> now): pressure comes back down close
    # to (but a hair above) the 9.0 healthy baseline — the baseline's MAD is tight enough
    # that even a modest few-unit residual reads as a full-strength deviation again
    # (found empirically), so a genuinely lower-severity "still recovering" read needs a
    # near-complete return, not just a partial one. The story stays distinct from the
    # flagship machine's own fully-resolved ending in how it got there (a shorter, milder
    # incident and a maintenance case that only just completed), not in the final number.
    recovery_start = now - timedelta(minutes=25)
    recovery_rows: list[dict[str, object]] = []

    def add_recovery(
        sensor: Sensor, value: float, t: datetime, *, circuit: uuid.UUID | None = None
    ) -> None:
        recovery_rows.append(
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

    steps = 25
    for i in range(steps):
        frac = (i + 1) / steps
        t = recovery_start + (now - recovery_start) * frac
        add_recovery(pressure, jitter(17.0 - 7.7 * frac, 0.15), t, circuit=circuit_id)
        add_recovery(pump_current, jitter(3.0, 0.05), t)
        add_recovery(reservoir, jitter(reservoir_value(t), 0.05), t)
        add_recovery(rpm, jitter(1450.0, 3.0), t)
        add_recovery(power, jitter(34.0 - 3.7 * frac, 0.6), t)
        for b in bearing_temps:
            add_recovery(b, jitter(41.0, 0.15), t)
        for v in vibrations:
            add_recovery(v, jitter(2.0, 0.03), t)

    async with database.session() as session:
        repo = TelemetryRepository(session)
        await repo.batch_insert_idempotent(recovery_rows)
        await session.commit()
    print(f"Seeded {len(recovery_rows)} partial-recovery telemetry rows")

    for _ in range(3):
        await reprocess(tenant_id, machine_id, recovery_start, now)
    print("Reprocessed rules over the recovery window")

    async with database.session() as session:
        maintenance = MaintenanceService(session)
        case = await maintenance.get(tenant_id, case.id)
        if case.state in (MaintenanceState.IN_PROGRESS, MaintenanceState.AWAITING_VERIFICATION):
            case = await maintenance.complete(
                tenant_id,
                case.id,
                classification=FeedbackClassification.TRUE_POSITIVE,
                confirmed_component="distributor",
                confirmed_finding="Partial blockage at the distributor outlet, partially cleared.",
                notes=(
                    "Pressure trending back toward baseline; re-inspect on next "
                    "scheduled visit to confirm full clearance."
                ),
                recorded_by="demo-technician",
            )
            await session.commit()
        print(f"Maintenance case {case.id} state: {case.state.value}")

    await database.dispose()
    print("")
    print(f"Recovering-asset story complete: machine_id={machine_id} incident_id={incident.id}")
    print(f"View at: http://localhost:3000/machines/{machine_id}")


if __name__ == "__main__":
    asyncio.run(main())
