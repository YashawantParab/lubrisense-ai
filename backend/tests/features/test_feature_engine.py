"""Database integration: PIT correctness, parity, idempotency, and ACTIVE baselines."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import BaselineState, BaselineStrategyType, Eligibility, SensorType
from app.features.config.policy import load_feature_policy
from app.features.materialization.materializer import FeatureMaterializer
from app.features.services.feature_engine import FeatureEngine
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


@pytest.mark.asyncio
async def test_point_in_time_determinism_train_serve_parity_and_idempotency(
    db_session: AsyncSession,
) -> None:
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
    as_of = datetime.now(UTC)
    start = as_of - timedelta(minutes=10)
    await insert_rows(
        db_session,
        [
            telemetry_row(
                tenant_id=tenant.id,
                sensor_id=sensor.id,
                machine_id=machine.id,
                circuit_id=circuit.id,
                source_timestamp=start + timedelta(minutes=index),
                value=10.0 + index / 10,
                measurement_type=SensorType.PRESSURE,
                sequence_number=index,
            )
            for index in range(10)
        ],
    )

    engine = FeatureEngine(db_session, POLICY)
    before = await engine.compute(tenant.id, machine.id, "LUBRICATION_ANOMALY_V1", as_of)
    repeated = await engine.compute(tenant.id, machine.id, "LUBRICATION_ANOMALY_V1", as_of)
    assert before.feature_vector_id == repeated.feature_vector_id
    assert before.feature_values == repeated.feature_values
    assert before.missing_features == repeated.missing_features

    materializer = FeatureMaterializer(db_session, POLICY)
    first_materialized = await materializer.materialize(
        tenant.id, machine.id, "LUBRICATION_ANOMALY_V1", as_of
    )
    second_materialized = await materializer.materialize(
        tenant.id, machine.id, "LUBRICATION_ANOMALY_V1", as_of
    )
    assert first_materialized.inserted is True
    assert second_materialized.inserted is False
    assert first_materialized.vector.feature_values == before.feature_values

    await insert_rows(
        db_session,
        [
            telemetry_row(
                tenant_id=tenant.id,
                sensor_id=sensor.id,
                machine_id=machine.id,
                circuit_id=circuit.id,
                source_timestamp=as_of + timedelta(minutes=5),
                value=99.0,
                measurement_type=SensorType.PRESSURE,
                sequence_number=99,
            )
        ],
    )
    after_future_insert = await engine.compute(
        tenant.id, machine.id, "LUBRICATION_ANOMALY_V1", as_of
    )
    assert after_future_insert.feature_values == before.feature_values
    assert after_future_insert.missing_features == before.missing_features


@pytest.mark.asyncio
async def test_only_active_baseline_is_used_and_ineligible_values_are_suppressed(
    db_session: AsyncSession,
) -> None:
    tenant, machine, _system, circuit, _bearing = await build_machine_with_topology(db_session)
    pressure = await make_topology_sensor(
        db_session, tenant, SensorType.PRESSURE, circuit_id=circuit.id
    )
    flow = await make_topology_sensor(db_session, tenant, SensorType.FLOW, circuit_id=circuit.id)
    await set_eligibility(db_session, tenant.id, pressure.id, machine.id, Eligibility.ELIGIBLE)
    await set_eligibility(db_session, tenant.id, flow.id, machine.id, Eligibility.INELIGIBLE)
    await create_active_baseline(
        db_session,
        tenant_id=tenant.id,
        sensor_id=pressure.id,
        machine_id=machine.id,
        measurement_type="PRESSURE",
        strategy=BaselineStrategyType.ROLLING_ASSET_BASELINE,
        context_key="",
        statistics=robust_stats(10.0, 1.0),
    )
    await create_active_baseline(
        db_session,
        tenant_id=tenant.id,
        sensor_id=pressure.id,
        machine_id=machine.id,
        measurement_type="PRESSURE",
        strategy=BaselineStrategyType.CONTEXTUAL_ASSET_BASELINE,
        context_key="stale-test",
        statistics=robust_stats(100.0, 1.0),
        state=BaselineState.STALE,
    )
    as_of = datetime.now(UTC)
    await insert_rows(
        db_session,
        [
            telemetry_row(
                tenant_id=tenant.id,
                sensor_id=pressure.id,
                machine_id=machine.id,
                circuit_id=circuit.id,
                source_timestamp=as_of,
                value=12.0,
                measurement_type=SensorType.PRESSURE,
            ),
            telemetry_row(
                tenant_id=tenant.id,
                sensor_id=flow.id,
                machine_id=machine.id,
                circuit_id=circuit.id,
                source_timestamp=as_of,
                value=0.0,
                measurement_type=SensorType.FLOW,
            ),
        ],
    )
    result = await FeatureEngine(db_session, POLICY).compute(
        tenant.id, machine.id, "LUBRICATION_ANOMALY_V1", as_of
    )
    assert result.feature_values["pressure.delta_from_baseline"] == 2.0
    assert result.baseline_versions["PRESSURE"]["fallback_source"] == "SENSOR_LEVEL"  # type: ignore[index]
    assert "flow.current" in result.missing_features
    assert result.feature_values["availability.has_flow_sensor"] is True
    assert result.quality_summary["suppressed_point_count"] == 1
