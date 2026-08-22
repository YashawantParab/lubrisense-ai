"""Demo scenario — a data-quality-limited machine (docs/HOSTED_DEPLOYMENT.md "10
meaningful synthetic scenarios" pass). Seeds Motor 013 (`L1-95FA-M013`, the
`lubrisense-demo` tenant) with otherwise-normal telemetry across the whole machine, but
marks its bearing-condition instrumentation (both `BEARING_TEMPERATURE` sensors and both
`VIBRATION_RMS` sensors — one coherent root cause: a shared junction box/signal
conditioner for the bearing monitoring subsystem showing suspected sensor drift) `UNUSABLE`
+ `INELIGIBLE`, while the lubrication-delivery instrumentation (pressure, reservoir level,
pump current, RPM) stays fully `TRUSTED`/`ELIGIBLE`. This is "diagnosis confidence limited
by a real quality issue on part of the machine", not "everything is broken".

Real, tested system behavior: `app.condition_intelligence.services.synthesis.
_quality_gate_verdict` only trips `SENSOR_OR_DATA_QUALITY_LIMITATION` once
`unusable_sensor_count / registered_sensor_count >= quality_gate.unusable_fraction_
threshold` (0.5, `condition_intelligence_v1.yaml`) — a fraction of the machine's *total*
registered sensors (8 for a full lubrication-chain machine: pressure, reservoir level, pump
current, RPM, 2x bearing temperature, 2x vibration), not "any one sensor is bad". Marking
only a single sensor (1/8 = 12.5%) never clears that threshold. Marking exactly the
4-sensor bearing-condition instrumentation group (4/8 = 50%) does, while leaving every
lubrication-delivery signal fully trusted — the closest honest match to "one subsystem's
instrumentation is unusable" this policy's threshold allows. See
`app.rules_engine.rules.quality.check_insufficient_trusted_data` for the parallel
rules-layer gate (`eligible_sensor_fraction < 0.5`), which this same split also clears.

Real `QualityIssue`/`QualityAssessment` rows are written via the actual
`QualityAssessmentRepository`/`QualityIssueRepository` (the same repositories
`app.data_quality.services.window_evaluator` uses for a real window-scoped issue) so the
Data Quality page has something real to show, not just a bare `SensorQualityState` flip.
No incident is created — `SENSOR_OR_DATA_QUALITY_LIMITATION` has no incident "family"
(`app.incidents.services.correlation.family_for_condition_type`), by design: a data-quality
problem is not itself equipment-condition evidence.

    uv run python scripts/seed_data_quality_issue.py

Safe to re-run: deletes and rebuilds only this one machine's own telemetry/state estimates
first (ADR-173); the quality-issue upsert is idempotent on `(tenant, sensor, rule_id,
rule_version)` while ACTIVE (`uq_quality_issue_active_window_scope`).
"""

from __future__ import annotations

import asyncio
import random
import uuid
from datetime import UTC, datetime, timedelta

from app.baselines.workers.backfill import backfill
from app.core.config import get_settings
from app.data_quality.domain.results import RuleIssue
from app.data_quality.repositories.quality_assessment_repository import (
    QualityAssessmentRepository,
)
from app.data_quality.repositories.quality_issue_repository import QualityIssueRepository
from app.domain.enums import (
    Eligibility,
    IssueSeverity,
    QualityDimension,
    QualityIssueType,
    QualityState,
)
from app.domain.models import Sensor
from app.incidents.services.incident_service import IncidentService
from app.infrastructure.database import Database
from app.repositories.telemetry import TelemetryRepository
from app.rules_engine.workers.reprocess import reprocess
from scripts._scenario_seed_common import (
    envelope,
    mark_sensor_quality,
    reset_machine_data,
    resolve_machine,
)

ASSET_CODE = "L1-95FA-M013"
DEVICE_ID = "data-quality-issue-seed"
_RULE_ID = "bearing_instrumentation_sensor_drift_suspected"
_RULE_VERSION = "1"


async def main() -> None:
    settings = get_settings()
    database = Database(settings)
    now = datetime.now(UTC)
    healthy_start = now - timedelta(hours=3)
    issue_start = now - timedelta(hours=1)

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

        rng = random.Random(20260821106)

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

        # Whole-machine telemetry is calm and normal throughout — the story here is a
        # sensor-quality problem, not a physical-condition problem. The bearing sensors
        # still report real values (drift, not silence) so the reading looks plausible on
        # a chart even though it is flagged untrustworthy.
        steps = 180
        for i in range(steps):
            t = healthy_start + (now - healthy_start) * (i / steps)
            add(pressure, jitter(9.0, 0.15), t, circuit=circuit_id)
            add(pump_current, jitter(3.0, 0.05), t)
            add(reservoir, jitter(58.0 - 0.01 * i, 0.05), t)
            add(rpm, jitter(1450.0, 3.0), t)
            for b in bearing_temps:
                add(b, jitter(42.0, 0.15), t)
            for v in vibrations:
                add(v, jitter(2.1, 0.03), t)

        repo = TelemetryRepository(session)
        await repo.batch_insert_idempotent(rows)
        await session.commit()
        print(f"Seeded {len(rows)} telemetry rows for machine={machine_id}")

        trusted_sensor_ids = [pressure.id, pump_current.id, reservoir.id, rpm.id]
        unusable_sensors = list(bearing_temps) + list(vibrations)

    for sid in trusted_sensor_ids:
        await mark_sensor_quality(
            database,
            tenant_id,
            machine_id,
            sid,
            quality_state=QualityState.TRUSTED,
            eligibility=Eligibility.ELIGIBLE,
            last_observed_at=now,
        )
    print(f"Marked {len(trusted_sensor_ids)} lubrication-delivery sensors ELIGIBLE/TRUSTED")

    for sid in trusted_sensor_ids:
        await backfill(tenant_id, sid, healthy_start, issue_start)
        await backfill(tenant_id, sid, healthy_start, issue_start)
    print("Built baselines for the trusted lubrication-delivery sensors")

    # Mark the bearing-condition instrumentation UNUSABLE/INELIGIBLE and write a real
    # window-scoped QualityIssue for each — same repositories the live data-quality-worker
    # uses for a real drift-suspicion finding.
    for sensor in unusable_sensors:
        await mark_sensor_quality(
            database,
            tenant_id,
            machine_id,
            sensor.id,
            quality_state=QualityState.UNUSABLE,
            eligibility=Eligibility.INELIGIBLE,
            last_observed_at=now,
        )
        async with database.session() as session:
            assessment = await QualityAssessmentRepository(session).create_window_assessment(
                tenant_id=tenant_id,
                sensor_id=sensor.id,
                machine_id=machine_id,
                window_start=issue_start,
                window_end=now,
                quality_state=QualityState.UNUSABLE,
                policy_version="1",
                rule_versions={_RULE_ID: _RULE_VERSION},
                metadata={"scenario": "data_quality_issue_seed"},
            )
            issue = RuleIssue(
                dimension=QualityDimension.SENSOR_HEALTH,
                issue_type=QualityIssueType.SENSOR_DRIFT_SUSPECTED,
                severity=IssueSeverity.ERROR,
                message=(
                    f"{sensor.name}: sustained drift from expected reading pattern suspected "
                    "on the bearing-condition instrumentation junction — readings no longer "
                    "trustworthy for condition assessment."
                ),
                rule_id=_RULE_ID,
                rule_version=_RULE_VERSION,
                evidence={"sensor_code": sensor.sensor_code, "window_hours": 1.0},
                window_start=issue_start,
                window_end=now,
            )
            await QualityIssueRepository(session).upsert_active_window_issue(
                tenant_id=tenant_id,
                sensor_id=sensor.id,
                machine_id=machine_id,
                assessment_id=assessment.id,
                issue=issue,
                policy_version="1",
            )
            await session.commit()
    print(
        f"Marked {len(unusable_sensors)} bearing-instrumentation sensors "
        "UNUSABLE/INELIGIBLE with a real QualityIssue"
    )

    for _ in range(3):
        await reprocess(tenant_id, machine_id, issue_start, now)
    print("Reprocessed rules over the issue window")

    async with database.session() as session:
        incidents = IncidentService(session)
        incident = await incidents.evaluate_machine(tenant_id, machine_id)
        await session.commit()
        if incident is None:
            print(
                "No incident created (expected) — data-quality limitation is "
                "not itself equipment-condition evidence."
            )
        else:
            print(
                f"WARNING: an incident was unexpectedly created ({incident.incident_type.value}) — "
                "investigate before using this machine as the data-quality demo scenario."
            )

    await database.dispose()
    print("")
    print(f"Data quality issue story complete: machine_id={machine_id}")
    print(f"View at: http://localhost:3000/machines/{machine_id}")


if __name__ == "__main__":
    asyncio.run(main())
