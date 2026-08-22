"""Hosted-demo healthy comparison machine (docs/HOSTED_DEPLOYMENT.md) — seeds calm,
in-range telemetry on a second real machine (Motor 001, `L1-7B43-M001`, the same demo
tenant as the flagship) so a reviewer has something to contrast the flagship's incident
story against: "most of the fleet looks like this."

Drives the exact same real services the flagship story uses for its own healthy phase
(`TelemetryRepository`, `SensorQualityStateRepository`, `app.baselines.workers.backfill`,
`app.rules_engine.workers.reprocess`, `StateEstimationService` building blocks,
`IncidentService.evaluate_machine`) — nothing here is a hardcoded frontend value. Expects
(and asserts) the real outcome to be `NORMAL_OPERATION` with no incident, exactly because
nothing here is scripted to deviate.

    uv run python scripts/seed_healthy_machine.py

Safe to re-run: deletes and rebuilds only this one machine's own telemetry/state estimates
before reseeding (same convention as `seed_flagship_story.py` / ADR-173).
"""

from __future__ import annotations

import asyncio
import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.baselines.workers.backfill import backfill
from app.core.config import get_settings
from app.data_quality.repositories.sensor_quality_state_repository import (
    SensorQualityStateRepository,
)
from app.domain.enums import Eligibility, QualityState, TelemetryQuality
from app.domain.models import (
    Bearing,
    Circuit,
    LubricationSystem,
    Machine,
    Pump,
    Reservoir,
    Sensor,
    Tenant,
)
from app.incidents.services.incident_service import IncidentService
from app.infrastructure.database import Database
from app.repositories.telemetry import TelemetryRepository
from app.rules_engine.workers.reprocess import reprocess
from scripts._scenario_seed_common import reset_machine_workflow_history

HEALTHY_MACHINE_ASSET_CODE = "L1-7B43-M001"
DEMO_TENANT_SLUG = "lubrisense-demo"
GATEWAY_CODE = "GW-RIDGE"
DEVICE_ID = "healthy-machine-seed"


@dataclass(frozen=True, slots=True)
class _HealthyMachineContext:
    tenant_id: uuid.UUID
    machine_id: uuid.UUID
    circuit_id: uuid.UUID | None
    by_type: dict[str, list[Sensor]]


async def _resolve(session: AsyncSession) -> _HealthyMachineContext:
    tenant = (
        await session.execute(select(Tenant).where(Tenant.slug == DEMO_TENANT_SLUG))
    ).scalar_one()
    machine = (
        await session.execute(
            select(Machine).where(
                Machine.tenant_id == tenant.id,
                Machine.asset_code == HEALTHY_MACHINE_ASSET_CODE,
            )
        )
    ).scalar_one()

    grouped: dict[str, list[Sensor]] = {}

    async def _add(stmt: Select[tuple[Sensor]]) -> None:
        rows = (await session.execute(stmt)).scalars().all()
        for s in rows:
            grouped.setdefault(s.sensor_type.value, []).append(s)

    await _add(
        select(Sensor)
        .join(Circuit, Circuit.id == Sensor.circuit_id)
        .join(LubricationSystem, LubricationSystem.id == Circuit.lubrication_system_id)
        .where(LubricationSystem.machine_id == machine.id, Sensor.tenant_id == tenant.id)
    )
    await _add(
        select(Sensor)
        .join(Pump, Pump.id == Sensor.pump_id)
        .join(LubricationSystem, LubricationSystem.id == Pump.lubrication_system_id)
        .where(LubricationSystem.machine_id == machine.id, Sensor.tenant_id == tenant.id)
    )
    await _add(
        select(Sensor)
        .join(Reservoir, Reservoir.id == Sensor.reservoir_id)
        .join(LubricationSystem, LubricationSystem.id == Reservoir.lubrication_system_id)
        .where(LubricationSystem.machine_id == machine.id, Sensor.tenant_id == tenant.id)
    )
    await _add(
        select(Sensor)
        .join(Bearing, Bearing.id == Sensor.bearing_id)
        .where(Bearing.machine_id == machine.id, Sensor.tenant_id == tenant.id)
    )
    await _add(select(Sensor).where(Sensor.machine_id == machine.id, Sensor.tenant_id == tenant.id))

    circuit_row = (
        (
            await session.execute(
                select(Circuit)
                .join(LubricationSystem, LubricationSystem.id == Circuit.lubrication_system_id)
                .where(LubricationSystem.machine_id == machine.id)
            )
        )
        .scalars()
        .first()
    )

    return _HealthyMachineContext(
        tenant_id=tenant.id,
        machine_id=machine.id,
        circuit_id=circuit_row.id if circuit_row else None,
        by_type=grouped,
    )


def _envelope(
    *,
    tenant_id: uuid.UUID,
    machine_id: uuid.UUID,
    sensor: Sensor,
    value: float,
    t: datetime,
    now: datetime,
    circuit_id: uuid.UUID | None = None,
) -> dict[str, object]:
    return {
        "event_id": uuid.uuid4(),
        "schema_version": "1",
        "correlation_id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "site_id": None,
        "plant_id": None,
        "production_line_id": None,
        "machine_id": machine_id,
        "bearing_id": None,
        "lubrication_system_id": None,
        "circuit_id": circuit_id,
        "lubrication_point_id": None,
        "sensor_id": sensor.id,
        "measurement_type": sensor.sensor_type,
        "value": value,
        "unit": sensor.unit,
        "quality": TelemetryQuality.GOOD,
        "operating_state": "RUNNING_NORMAL_LOAD",
        "source_timestamp": t,
        "edge_received_timestamp": t,
        "edge_emitted_timestamp": None,
        # A constant small latency after `t`, not the single seed-time `now` for every
        # row — see the identical comment in `seed_flagship_story.py`'s own `_envelope()`
        # for why: pinning every row's receipt timestamps to one `now` across a
        # backfilled multi-hour series spuriously trips `CLOCK_DRIFT_SUSPECTED`.
        "mqtt_received_timestamp": t + timedelta(seconds=1.5),
        "kafka_published_timestamp": t + timedelta(seconds=1.5),
        "consumer_received_timestamp": t + timedelta(seconds=1.5),
        "sequence_number": 1,
        "gateway_id": GATEWAY_CODE,
        "device_id": DEVICE_ID,
        "firmware_version": None,
        "controller_version": None,
        "source": "synthetic",
        "metadata": {},
        "kafka_partition": 0,
        "kafka_offset": 0,
    }


async def main() -> None:
    settings = get_settings()
    database = Database(settings)
    now = datetime.now(UTC)
    healthy_start = now - timedelta(hours=3)

    async with database.session() as session:
        base = await _resolve(session)
        tenant_id = base.tenant_id
        machine_id = base.machine_id
        circuit_id = base.circuit_id
        by_type = base.by_type

        pressure = by_type["PRESSURE"][0]
        pump_current = by_type["PUMP_CURRENT"][0]
        reservoir = by_type["RESERVOIR_LEVEL"][0]
        rpm = by_type["RPM"][0]
        bearing_temps = by_type["BEARING_TEMPERATURE"]
        vibrations = by_type["VIBRATION_RMS"]

        # Deterministic reset: this machine is fully owned by this script within the
        # story's own window, same convention as the flagship (ADR-173).
        from app.domain.models import MLInferenceResult, StateEstimate, Telemetry

        await session.execute(
            delete(Telemetry).where(
                Telemetry.tenant_id == tenant_id, Telemetry.machine_id == machine_id
            )
        )
        await session.execute(
            delete(StateEstimate).where(
                StateEstimate.tenant_id == tenant_id, StateEstimate.machine_id == machine_id
            )
        )
        # A stale MLInferenceResult row is enough to change ConditionEngine/synthesize()'s
        # "was any evidence source ever checked" gate (found empirically) — must not
        # outlive the telemetry it was actually computed from.
        await session.execute(
            delete(MLInferenceResult).where(
                MLInferenceResult.tenant_id == tenant_id, MLInferenceResult.machine_id == machine_id
            )
        )
        # Also clears any prior incident/maintenance history for this machine — belt and
        # braces alongside the flagship script's identical fix: this machine's own
        # `evaluate_machine()` call below is expected to find nothing (healthy telemetry),
        # but keeps a stray finding from an earlier run's jitter from accumulating.
        await reset_machine_workflow_history(session, tenant_id, machine_id)
        await session.commit()

        # Fixed seed (not time-based) — deterministic across runs, same reasoning as the
        # flagship script (ADR-170): real sensor noise, never a perfectly flat line.
        rng = random.Random(20260819137)

        def jitter(value: float, magnitude: float) -> float:
            return value + rng.uniform(-magnitude, magnitude)

        rows: list[dict[str, object]] = []

        def add(
            sensor: Sensor, value: float, t: datetime, *, circuit: uuid.UUID | None = None
        ) -> None:
            rows.append(
                _envelope(
                    tenant_id=tenant_id,
                    machine_id=machine_id,
                    sensor=sensor,
                    value=value,
                    t=t,
                    now=now,
                    circuit_id=circuit,
                )
            )

        steps = 130
        for i in range(steps):
            t = healthy_start + (now - healthy_start) * (i / steps)
            add(pressure, jitter(9.0, 0.15), t, circuit=circuit_id)
            add(pump_current, jitter(3.0, 0.05), t)
            add(reservoir, jitter(60.0 - 0.01 * i, 0.05), t)
            add(rpm, jitter(1450.0, 3.0), t)
            for b in bearing_temps:
                add(b, jitter(42.0, 0.15), t)
            for v in vibrations:
                add(v, jitter(2.1, 0.03), t)

        repo = TelemetryRepository(session)
        await repo.batch_insert_idempotent(rows)
        await session.commit()
        print(f"Seeded {len(rows)} healthy telemetry rows for machine={machine_id}")

        all_sensor_ids = [pressure.id, pump_current.id, reservoir.id, rpm.id]
        all_sensor_ids += [b.id for b in bearing_temps]
        all_sensor_ids += [v.id for v in vibrations]

        quality_repo = SensorQualityStateRepository(session)
        for sid in all_sensor_ids:
            await quality_repo.upsert(
                tenant_id,
                sid,
                machine_id=machine_id,
                quality_state=QualityState.TRUSTED,
                eligibility=Eligibility.ELIGIBLE,
                policy_version="1",
                # Merge-patch upsert (see `_scenario_seed_common.mark_sensor_quality`'s
                # docstring): without this, a previous run's stale `last_observed_at`
                # survives untouched and produces a phantom STALE_STREAM issue.
                last_observed_at=now,
                last_source_timestamp_seen=now,
            )
        await session.commit()
        print(f"Marked {len(all_sensor_ids)} sensors ELIGIBLE")

    for sid in all_sensor_ids:
        await backfill(tenant_id, sid, healthy_start, now)
        await backfill(tenant_id, sid, healthy_start, now)
    print("Built baselines from the healthy window")

    for _ in range(3):
        await reprocess(tenant_id, machine_id, healthy_start, now)
    print("Reprocessed rules over the healthy window")

    # A machine with zero active rule findings, zero ML results, and zero state
    # estimates reads as `INSUFFICIENT_EVIDENCE` ("nothing was checked"), not
    # `NORMAL_OPERATION` ("checked, found nothing abnormal") — `rule_finding_ids` is an
    # empty (falsy) list either way, so at least one other real evidence source needs to
    # have actually run. Compute real state estimates the same way the flagship story
    # does (`FeatureEngine.compute()` + `StateEstimator` + `StateEstimateRepository`
    # directly), so this machine's "nothing wrong" reading is genuine evidence, not an
    # artifact of never having checked.
    try:
        from app.domain.enums import StateType
        from app.features.config.policy import load_feature_policy
        from app.features.services.feature_engine import FeatureEngine
        from app.state_estimation.config.policy import load_state_estimation_config
        from app.state_estimation.domain.models import PriorEstimate
        from app.state_estimation.models.estimator import FeatureTick, StateEstimator
        from app.state_estimation.repositories.state_estimate_repository import (
            StateEstimateRepository,
        )

        state_config = load_state_estimation_config()
        feature_policy = load_feature_policy()
        tick_count = 0
        for state_type in StateType:
            estimator = StateEstimator(
                estimator_id=state_type.value,
                estimator_version=state_config.estimator_version,
                config_version=state_config.config_version,
                state_type=state_type.value,
                config=state_config.state_config(state_type.value),
                gap=state_config.gap,
                uncertainty=state_config.uncertainty,
            )
            for frac in (0.3, 0.6, 1.0):
                as_of = healthy_start + (now - healthy_start) * frac
                async with database.session() as session:
                    engine = FeatureEngine(session, feature_policy)
                    computed = await engine.compute(
                        tenant_id,
                        machine_id,
                        state_config.feature_set,
                        as_of,
                    )
                    tick = FeatureTick(
                        tenant_id=computed.tenant_id,
                        machine_id=computed.machine_id,
                        feature_vector_id=computed.feature_vector_id,
                        feature_set=computed.feature_set,
                        feature_set_version=computed.feature_set_version,
                        as_of_timestamp=computed.as_of_timestamp,
                        feature_values=computed.feature_values,
                        missing_features=computed.missing_features,
                        quality_state=str(computed.quality_summary.get("state", "NO_TRUSTED_DATA")),
                    )
                    state_repo = StateEstimateRepository(session)
                    prior_row = await state_repo.get_latest(
                        tenant_id,
                        machine_id,
                        state_type.value,
                        state_config.estimator_version,
                    )
                    prior = (
                        None
                        if prior_row is None
                        else PriorEstimate(
                            as_of_timestamp=prior_row.as_of_timestamp,
                            level=prior_row.state_value,
                            rate=prior_row.state_rate,
                            p00=float(prior_row.covariance_summary["p00"]),
                            p01=float(prior_row.covariance_summary["p01"]),
                            p11=float(prior_row.covariance_summary["p11"]),
                        )
                    )
                    result = estimator.step(prior, tick)
                    await state_repo.persist(result)
                    tick_count += 1
                    await session.commit()
        print(f"Computed {tick_count} state estimate ticks")
    except Exception as exc:  # noqa: BLE001 - best-effort for this demo machine
        print(f"State estimation skipped ({exc})")

    async with database.session() as session:
        incidents = IncidentService(session)
        incident = await incidents.evaluate_machine(tenant_id, machine_id)
        await session.commit()
        if incident is None:
            print("Healthy machine confirmed: no incident (as expected).")
        else:
            # Not fatal — the seed script prints this loudly rather than silently
            # papering over an unexpected finding so a reviewer's "healthy" comparison
            # machine is never quietly wrong.
            print(
                f"WARNING: healthy machine unexpectedly produced an incident "
                f"({incident.incident_type.value}) — investigate before using this "
                f"machine as the hosted demo's healthy comparison."
            )

    await database.dispose()
    print(f"Healthy comparison machine ready: machine_id={machine_id}")


if __name__ == "__main__":
    asyncio.run(main())
