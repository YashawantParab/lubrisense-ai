"""Database integration: `PrognosticEngine.forecast_machine()` against real Postgres and
real Phase 12 `StateEstimate` rows (persisted via the real `StateEstimator`, mirroring
`tests/state_estimation/test_persistence_and_replay.py`'s pattern)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Machine, StateEstimate, Tenant
from app.prognostics.services.prognostic_engine import (
    PrognosticEngine,
    PrognosticEngineMachineNotFoundError,
)
from app.state_estimation.config.policy import load_state_estimation_config
from tests.rules_engine.helpers import build_machine_with_topology

STATE_CONFIG = load_state_estimation_config()


async def _seed_state_estimate(
    session: AsyncSession,
    tenant: Tenant,
    machine: Machine,
    *,
    state_type: str,
    level: float,
    rate: float,
    trend: str,
    uncertainty: str,
    prediction_only: bool = False,
) -> StateEstimate:
    now = datetime.now(UTC)
    estimate = StateEstimate(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        machine_id=machine.id,
        component_id=None,
        state_type=state_type,
        as_of_timestamp=now,
        state_value=level,
        state_rate=rate,
        trend=trend,
        uncertainty=uncertainty,
        covariance_summary={"p00": 0.01, "p01": 0.0, "p11": 0.0001},
        estimator_id=state_type,
        estimator_version=STATE_CONFIG.estimator_version,
        config_version=STATE_CONFIG.config_version,
        feature_set=STATE_CONFIG.feature_set,
        feature_set_version=STATE_CONFIG.feature_set_version,
        feature_vector_id=uuid.uuid4(),
        dt_seconds=600.0,
        prediction_only=prediction_only,
        observations_used=[],
        observations_missing=[],
        quality_summary={"state": "TRUSTED"},
    )
    session.add(estimate)
    await session.flush()
    return estimate


@pytest.mark.asyncio
async def test_forecast_unknown_machine_raises(db_session: AsyncSession) -> None:
    engine = PrognosticEngine(db_session)
    with pytest.raises(PrognosticEngineMachineNotFoundError):
        await engine.forecast_machine(uuid.uuid4(), uuid.uuid4())


@pytest.mark.asyncio
async def test_forecast_with_no_state_estimates_returns_empty(db_session: AsyncSession) -> None:
    tenant, machine, _system, _circuit, _bearing = await build_machine_with_topology(db_session)
    engine = PrognosticEngine(db_session)
    results = await engine.forecast_machine(tenant.id, machine.id)
    assert results == []


@pytest.mark.asyncio
async def test_forecast_produces_one_row_per_horizon_per_state_type(
    db_session: AsyncSession,
) -> None:
    tenant, machine, _system, _circuit, _bearing = await build_machine_with_topology(db_session)
    for _ in range(4):
        await _seed_state_estimate(
            db_session,
            tenant,
            machine,
            state_type="LUBRICATION_DELIVERY_STATE",
            level=0.3,
            rate=0.0001,
            trend="DETERIORATING",
            uncertainty="LOW",
        )

    engine = PrognosticEngine(db_session)
    results = await engine.forecast_machine(tenant.id, machine.id)

    delivery_results = [r for r in results if r.state_type.value == "LUBRICATION_DELIVERY_STATE"]
    assert {r.horizon.value for r in delivery_results} == {
        "ONE_HOUR",
        "SIX_HOURS",
        "TWENTY_FOUR_HOURS",
    }
    assert all(r.status.value == "OK" for r in delivery_results)
    assert all(r.predicted_state_at_horizon is not None for r in delivery_results)


@pytest.mark.asyncio
async def test_forecast_reports_no_reliable_forecast_for_high_uncertainty(
    db_session: AsyncSession,
) -> None:
    tenant, machine, _system, _circuit, _bearing = await build_machine_with_topology(db_session)
    await _seed_state_estimate(
        db_session,
        tenant,
        machine,
        state_type="LUBRICATION_DELIVERY_STATE",
        level=0.3,
        rate=0.0,
        trend="UNKNOWN",
        uncertainty="HIGH",
        prediction_only=True,
    )

    engine = PrognosticEngine(db_session)
    results = await engine.forecast_machine(tenant.id, machine.id)
    delivery_results = [r for r in results if r.state_type.value == "LUBRICATION_DELIVERY_STATE"]
    assert all(r.status.value == "NO_RELIABLE_FORECAST" for r in delivery_results)
    assert all(r.predicted_state_at_horizon is None for r in delivery_results)


@pytest.mark.asyncio
async def test_healthy_stable_state_never_forecasts_a_threshold_crossing(
    db_session: AsyncSession,
) -> None:
    tenant, machine, _system, _circuit, _bearing = await build_machine_with_topology(db_session)
    for _ in range(4):
        await _seed_state_estimate(
            db_session,
            tenant,
            machine,
            state_type="LUBRICATION_DELIVERY_STATE",
            level=0.04,
            rate=0.0,
            trend="STABLE",
            uncertainty="LOW",
        )

    engine = PrognosticEngine(db_session)
    results = await engine.forecast_machine(tenant.id, machine.id)
    delivery_results = [r for r in results if r.state_type.value == "LUBRICATION_DELIVERY_STATE"]
    assert all(r.estimated_threshold_crossing_time is None for r in delivery_results)


@pytest.mark.asyncio
async def test_independent_bearing_forecast_stays_separate_from_delivery(
    db_session: AsyncSession,
) -> None:
    """Phase 15 brief §15.9: bearing forecast worsens while delivery forecast stays
    broadly nominal."""
    tenant, machine, _system, _circuit, _bearing = await build_machine_with_topology(db_session)
    for _ in range(4):
        await _seed_state_estimate(
            db_session,
            tenant,
            machine,
            state_type="LUBRICATION_DELIVERY_STATE",
            level=0.04,
            rate=0.0,
            trend="STABLE",
            uncertainty="LOW",
        )
        await _seed_state_estimate(
            db_session,
            tenant,
            machine,
            state_type="BEARING_CONDITION_STATE",
            level=0.6,
            rate=0.0002,
            trend="DETERIORATING",
            uncertainty="LOW",
        )

    engine = PrognosticEngine(db_session)
    results = await engine.forecast_machine(tenant.id, machine.id)

    delivery = [r for r in results if r.state_type.value == "LUBRICATION_DELIVERY_STATE"]
    bearing = [r for r in results if r.state_type.value == "BEARING_CONDITION_STATE"]
    assert all(r.current_state < 0.1 for r in delivery)
    assert all(r.current_state > 0.5 for r in bearing)
    assert any(
        r.predicted_state_at_horizon is not None and r.predicted_state_at_horizon > 0.6
        for r in bearing
    )
