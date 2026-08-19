"""Database integration: persistence, idempotency, historical replay, and online
continuation — against real Postgres, real `FeatureVector` rows (via the unchanged Phase
10 `FeatureMaterializer`), and the real `StateEstimateRepository`/`ReplayService`/
`StateEstimationService`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import BaselineStrategyType, Eligibility, SensorType
from app.domain.models import Machine, Tenant
from app.features.config.policy import load_feature_policy
from app.features.materialization.materializer import FeatureMaterializer
from app.state_estimation.services.replay_service import ReplayService
from app.state_estimation.services.state_estimation_service import StateEstimationService
from tests.rules_engine.helpers import (
    build_machine_with_topology,
    create_active_baseline,
    insert_rows,
    make_topology_sensor,
    robust_stats,
    set_eligibility,
    telemetry_row,
)

POLICY = load_feature_policy()


async def _seed_pressure_history(
    db_session: AsyncSession, *, ticks: int, interval_minutes: int = 10
) -> tuple[Tenant, Machine, datetime]:
    tenant, machine, _system, circuit, _bearing = await build_machine_with_topology(db_session)
    sensor = await make_topology_sensor(
        db_session, tenant, SensorType.PRESSURE, circuit_id=circuit.id
    )
    await set_eligibility(db_session, tenant.id, sensor.id, machine.id, Eligibility.ELIGIBLE)
    await create_active_baseline(
        db_session,
        tenant_id=tenant.id,
        sensor_id=sensor.id,
        machine_id=machine.id,
        measurement_type="PRESSURE",
        strategy=BaselineStrategyType.ROLLING_ASSET_BASELINE,
        context_key="",
        statistics=robust_stats(10.0, 0.5),
    )
    start = datetime.now(UTC) - timedelta(hours=6)
    await insert_rows(
        db_session,
        [
            telemetry_row(
                tenant_id=tenant.id,
                sensor_id=sensor.id,
                machine_id=machine.id,
                circuit_id=circuit.id,
                source_timestamp=start + timedelta(minutes=interval_minutes * index),
                value=10.0 + index * 0.3,
                measurement_type=SensorType.PRESSURE,
                sequence_number=index,
            )
            for index in range(ticks)
        ],
    )
    return tenant, machine, start


@pytest.mark.asyncio
async def test_replay_persists_one_estimate_per_vector_per_state_type(
    db_session: AsyncSession,
) -> None:
    tenant, machine, start = await _seed_pressure_history(db_session, ticks=6)
    materializer = FeatureMaterializer(db_session, POLICY)
    as_of_times = [start + timedelta(minutes=10 * i) for i in range(6)]
    for as_of in as_of_times:
        await materializer.materialize(tenant.id, machine.id, "STATE_ESTIMATION_V1", as_of)

    replay = ReplayService(db_session)
    counts = await replay.replay_machine(
        tenant.id,
        machine.id,
        start - timedelta(minutes=1),
        as_of_times[-1] + timedelta(minutes=1),
    )
    assert counts["LUBRICATION_DELIVERY_STATE"] == 6
    assert counts["BEARING_CONDITION_STATE"] == 6


@pytest.mark.asyncio
async def test_replay_is_idempotent_over_the_same_window(db_session: AsyncSession) -> None:
    tenant, machine, start = await _seed_pressure_history(db_session, ticks=4)
    materializer = FeatureMaterializer(db_session, POLICY)
    as_of_times = [start + timedelta(minutes=10 * i) for i in range(4)]
    for as_of in as_of_times:
        await materializer.materialize(tenant.id, machine.id, "STATE_ESTIMATION_V1", as_of)

    replay = ReplayService(db_session)
    window = (start - timedelta(minutes=1), as_of_times[-1] + timedelta(minutes=1))
    first_pass = await replay.replay_machine(tenant.id, machine.id, *window)
    second_pass = await replay.replay_machine(tenant.id, machine.id, *window)

    assert first_pass["LUBRICATION_DELIVERY_STATE"] == 4
    assert second_pass["LUBRICATION_DELIVERY_STATE"] == 0
    assert second_pass["BEARING_CONDITION_STATE"] == 0


@pytest.mark.asyncio
async def test_replay_processes_ticks_in_ascending_time_order(db_session: AsyncSession) -> None:
    """The pressure signal ramps upward across the seeded ticks, so a delivery-state replay
    processed in ascending order should show its final estimate reflecting the *last*
    tick's evidence, not the first."""
    tenant, machine, start = await _seed_pressure_history(db_session, ticks=8)
    materializer = FeatureMaterializer(db_session, POLICY)
    as_of_times = [start + timedelta(minutes=10 * i) for i in range(8)]
    for as_of in as_of_times:
        await materializer.materialize(tenant.id, machine.id, "STATE_ESTIMATION_V1", as_of)

    replay = ReplayService(db_session)
    await replay.replay_machine(
        tenant.id, machine.id, start - timedelta(minutes=1), as_of_times[-1] + timedelta(minutes=1)
    )

    last_row = await replay._estimates.get_latest(  # noqa: SLF001 - direct repo check in test
        tenant.id, machine.id, "LUBRICATION_DELIVERY_STATE", replay._config.estimator_version
    )
    assert last_row is not None
    assert last_row.as_of_timestamp == as_of_times[-1]


@pytest.mark.asyncio
async def test_online_latest_continues_from_replayed_history(db_session: AsyncSession) -> None:
    tenant, machine, start = await _seed_pressure_history(db_session, ticks=3)
    materializer = FeatureMaterializer(db_session, POLICY)
    as_of_times = [start + timedelta(minutes=10 * i) for i in range(3)]
    for as_of in as_of_times:
        await materializer.materialize(tenant.id, machine.id, "STATE_ESTIMATION_V1", as_of)

    replay = ReplayService(db_session)
    await replay.replay_machine(
        tenant.id, machine.id, start - timedelta(minutes=1), as_of_times[-1] + timedelta(minutes=1)
    )

    service = StateEstimationService(db_session, POLICY)
    results = await service.compute_and_persist_latest(tenant.id, machine.id)
    delivery = results["LUBRICATION_DELIVERY_STATE"]
    assert delivery.as_of_timestamp >= as_of_times[-1]
    assert delivery.dt_seconds >= 0.0
