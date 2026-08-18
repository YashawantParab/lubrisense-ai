"""Integration tests for `RuleEngine` against live Postgres — quality gating,
ACTIVE-baseline-only consumption, cross-signal pattern differentiation, idempotency, and
finding lifecycle (Phase 9 brief §35-§43, §21-§22, §28-§29).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.baselines.config.policy import load_baseline_policy
from app.domain.enums import (
    BaselineState,
    BaselineStrategyType,
    Eligibility,
    RuleFindingState,
    RuleFindingType,
    SensorType,
)
from app.rules_engine.config.policy import load_rules_policy
from app.rules_engine.repositories.rule_finding_repository import RuleFindingRepository
from app.rules_engine.services.rule_engine import RuleEngine
from tests.rules_engine.helpers import (
    build_machine_with_topology,
    create_active_baseline,
    insert_rows,
    make_topology_sensor,
    robust_stats,
    set_eligibility,
    telemetry_row,
)

BASELINE_POLICY = load_baseline_policy()
RULES_POLICY = load_rules_policy()


def _times(start: datetime, count: int, step_seconds: float = 5.0) -> list[datetime]:
    return [start + timedelta(seconds=step_seconds * i) for i in range(count)]


async def _run_cycles(engine: RuleEngine, tenant_id, machine_id, now, window, cycles: int = 3):
    result = None
    for _ in range(cycles):
        result = await engine.evaluate_machine(tenant_id, machine_id, now, window_override=window)
    return result


@pytest.mark.asyncio
async def test_ineligible_sensor_never_creates_finding(db_session: AsyncSession) -> None:
    tenant, machine, system, circuit, _bearing = await build_machine_with_topology(db_session)
    sensor = await make_topology_sensor(
        db_session, tenant, SensorType.PRESSURE, circuit_id=circuit.id
    )
    now = datetime.now(UTC)
    start = now - timedelta(hours=1)
    await create_active_baseline(
        db_session,
        tenant_id=tenant.id,
        sensor_id=sensor.id,
        machine_id=machine.id,
        measurement_type="PRESSURE",
        strategy=BaselineStrategyType.ROLLING_ASSET_BASELINE,
        context_key="",
        statistics=robust_stats(median=9.0, mad=0.5),
    )

    telemetry = [
        telemetry_row(
            tenant_id=tenant.id,
            sensor_id=sensor.id,
            machine_id=machine.id,
            circuit_id=circuit.id,
            source_timestamp=t,
            value=25.0,
            measurement_type=SensorType.PRESSURE,
        )
        for t in _times(start, 30)
    ]
    await insert_rows(db_session, telemetry)
    await set_eligibility(db_session, tenant.id, sensor.id, machine.id, Eligibility.INELIGIBLE)

    engine = RuleEngine(db_session, BASELINE_POLICY, RULES_POLICY)
    await _run_cycles(engine, tenant.id, machine.id, now, (start, now))

    finding_repo = RuleFindingRepository(db_session)
    findings = await finding_repo.list_current_for_machine(tenant.id, machine.id)
    pressure_findings = [
        f for f in findings if f.finding_type == RuleFindingType.PRESSURE_ABOVE_CONTEXTUAL_BASELINE
    ]
    assert pressure_findings == []


@pytest.mark.asyncio
async def test_insufficient_trusted_data_suppresses_equipment_findings(
    db_session: AsyncSession,
) -> None:
    """Mandatory (brief §40/§41): when too few sensors are eligible, only
    INSUFFICIENT_TRUSTED_DATA may fire — never an equipment-condition finding built on
    untrustworthy data."""
    tenant, machine, system, circuit, _bearing = await build_machine_with_topology(db_session)
    pressure_sensor = await make_topology_sensor(
        db_session, tenant, SensorType.PRESSURE, circuit_id=circuit.id
    )
    flow_sensor = await make_topology_sensor(
        db_session, tenant, SensorType.FLOW, circuit_id=circuit.id
    )
    now = datetime.now(UTC)
    start = now - timedelta(hours=1)

    for sensor, mtype, value in (
        (pressure_sensor, SensorType.PRESSURE, 25.0),
        (flow_sensor, SensorType.FLOW, 1.0),
    ):
        await create_active_baseline(
            db_session,
            tenant_id=tenant.id,
            sensor_id=sensor.id,
            machine_id=machine.id,
            measurement_type=mtype.value,
            strategy=BaselineStrategyType.ROLLING_ASSET_BASELINE,
            context_key="",
            statistics=robust_stats(median=9.0, mad=0.5),
        )
        rows = [
            telemetry_row(
                tenant_id=tenant.id,
                sensor_id=sensor.id,
                machine_id=machine.id,
                circuit_id=circuit.id,
                source_timestamp=t,
                value=value,
                measurement_type=mtype,
            )
            for t in _times(start, 30)
        ]
        await insert_rows(db_session, rows)

    # Both sensors ineligible -> eligible_sensor_fraction = 0.0, below the configured
    # minimum (default 0.5).
    await set_eligibility(
        db_session, tenant.id, pressure_sensor.id, machine.id, Eligibility.INELIGIBLE
    )
    await set_eligibility(db_session, tenant.id, flow_sensor.id, machine.id, Eligibility.INELIGIBLE)

    engine = RuleEngine(db_session, BASELINE_POLICY, RULES_POLICY)
    await engine.evaluate_machine(tenant.id, machine.id, now, window_override=(start, now))

    finding_repo = RuleFindingRepository(db_session)
    findings = await finding_repo.list_current_for_machine(tenant.id, machine.id)
    finding_types = {f.finding_type for f in findings}
    assert finding_types == {RuleFindingType.INSUFFICIENT_TRUSTED_DATA}


@pytest.mark.asyncio
async def test_only_active_baseline_consumed_not_stale(db_session: AsyncSession) -> None:
    """Mandatory (brief §43): a STALE baseline must never be used to judge a deviation —
    only ACTIVE baselines are consumed."""
    tenant, machine, system, circuit, _bearing = await build_machine_with_topology(db_session)
    sensor = await make_topology_sensor(
        db_session, tenant, SensorType.PRESSURE, circuit_id=circuit.id
    )
    now = datetime.now(UTC)
    start = now - timedelta(hours=1)

    # A STALE baseline claiming a wildly different (high) median — if the engine ever used
    # this, an observed value of 9.0 would look like a strong *below*-baseline deviation
    # rather than the near-exact match it should register against nothing/engineering
    # reference instead.
    await create_active_baseline(
        db_session,
        tenant_id=tenant.id,
        sensor_id=sensor.id,
        machine_id=machine.id,
        measurement_type="PRESSURE",
        strategy=BaselineStrategyType.ROLLING_ASSET_BASELINE,
        context_key="",
        statistics=robust_stats(median=90.0, mad=0.5),
        state=BaselineState.STALE,
    )

    rows = [
        telemetry_row(
            tenant_id=tenant.id,
            sensor_id=sensor.id,
            machine_id=machine.id,
            circuit_id=circuit.id,
            source_timestamp=t,
            value=9.0,
            measurement_type=SensorType.PRESSURE,
        )
        for t in _times(start, 30)
    ]
    await insert_rows(db_session, rows)
    await set_eligibility(db_session, tenant.id, sensor.id, machine.id, Eligibility.ELIGIBLE)

    engine = RuleEngine(db_session, BASELINE_POLICY, RULES_POLICY)
    context = await engine._build_context(tenant.id, machine.id, now, (start, now))  # noqa: SLF001 - white-box check

    pressure_signals = context.signals_for("PRESSURE")
    assert len(pressure_signals) == 1
    # The STALE row must never be reflected — baseline_median must NOT be 90.0.
    assert pressure_signals[0].baseline_median != 90.0


@pytest.mark.asyncio
async def test_restriction_pattern_fires_end_to_end(db_session: AsyncSession) -> None:
    tenant, machine, system, circuit, _bearing = await build_machine_with_topology(db_session)
    pressure_sensor = await make_topology_sensor(
        db_session, tenant, SensorType.PRESSURE, circuit_id=circuit.id
    )
    flow_sensor = await make_topology_sensor(
        db_session, tenant, SensorType.FLOW, circuit_id=circuit.id
    )
    now = datetime.now(UTC)
    start = now - timedelta(hours=1)

    await create_active_baseline(
        db_session,
        tenant_id=tenant.id,
        sensor_id=pressure_sensor.id,
        machine_id=machine.id,
        measurement_type="PRESSURE",
        strategy=BaselineStrategyType.ROLLING_ASSET_BASELINE,
        context_key="",
        statistics=robust_stats(median=9.0, mad=0.5),
    )
    await create_active_baseline(
        db_session,
        tenant_id=tenant.id,
        sensor_id=flow_sensor.id,
        machine_id=machine.id,
        measurement_type="FLOW",
        strategy=BaselineStrategyType.ROLLING_ASSET_BASELINE,
        context_key="",
        statistics=robust_stats(median=100.0, mad=5.0),
    )

    pressure_rows = [
        telemetry_row(
            tenant_id=tenant.id,
            sensor_id=pressure_sensor.id,
            machine_id=machine.id,
            circuit_id=circuit.id,
            source_timestamp=t,
            value=25.0,  # far above baseline median -> PRESSURE_ABOVE
            measurement_type=SensorType.PRESSURE,
        )
        for t in _times(start, 30)
    ]
    flow_rows = [
        telemetry_row(
            tenant_id=tenant.id,
            sensor_id=flow_sensor.id,
            machine_id=machine.id,
            circuit_id=circuit.id,
            source_timestamp=t,
            value=20.0,  # far below baseline median -> FLOW_BELOW
            measurement_type=SensorType.FLOW,
        )
        for t in _times(start, 30)
    ]
    await insert_rows(db_session, pressure_rows + flow_rows)
    await set_eligibility(
        db_session, tenant.id, pressure_sensor.id, machine.id, Eligibility.ELIGIBLE
    )
    await set_eligibility(db_session, tenant.id, flow_sensor.id, machine.id, Eligibility.ELIGIBLE)

    engine = RuleEngine(db_session, BASELINE_POLICY, RULES_POLICY)
    await _run_cycles(engine, tenant.id, machine.id, now, (start, now), cycles=3)

    finding_repo = RuleFindingRepository(db_session)
    findings = await finding_repo.list_current_for_machine(tenant.id, machine.id)
    restriction = [
        f for f in findings if f.finding_type == RuleFindingType.FLOW_PRESSURE_RESTRICTION_PATTERN
    ]
    assert len(restriction) == 1
    assert restriction[0].state == RuleFindingState.ACTIVE
    assert "required_signals" in restriction[0].evidence
    assert restriction[0].limitations  # never empty for a cross-signal pattern

    # Leakage must NOT also fire — pressure is elevated, which is the defining exclusion.
    leakage = [
        f for f in findings if f.finding_type == RuleFindingType.FLOW_PRESSURE_LEAKAGE_PATTERN
    ]
    assert leakage == []


@pytest.mark.asyncio
async def test_idempotent_reevaluation_does_not_duplicate_active_finding(
    db_session: AsyncSession,
) -> None:
    tenant, machine, system, circuit, _bearing = await build_machine_with_topology(db_session)
    sensor = await make_topology_sensor(
        db_session, tenant, SensorType.PRESSURE, circuit_id=circuit.id
    )
    now = datetime.now(UTC)
    start = now - timedelta(hours=1)
    await create_active_baseline(
        db_session,
        tenant_id=tenant.id,
        sensor_id=sensor.id,
        machine_id=machine.id,
        measurement_type="PRESSURE",
        strategy=BaselineStrategyType.ROLLING_ASSET_BASELINE,
        context_key="",
        statistics=robust_stats(median=9.0, mad=0.5),
    )

    rows = [
        telemetry_row(
            tenant_id=tenant.id,
            sensor_id=sensor.id,
            machine_id=machine.id,
            circuit_id=circuit.id,
            source_timestamp=t,
            value=25.0,
            measurement_type=SensorType.PRESSURE,
        )
        for t in _times(start, 30)
    ]
    await insert_rows(db_session, rows)
    await set_eligibility(db_session, tenant.id, sensor.id, machine.id, Eligibility.ELIGIBLE)

    engine = RuleEngine(db_session, BASELINE_POLICY, RULES_POLICY)
    await _run_cycles(engine, tenant.id, machine.id, now, (start, now), cycles=3)
    # A fourth, fifth, sixth identical cycle should never create a second row.
    await _run_cycles(engine, tenant.id, machine.id, now, (start, now), cycles=3)

    finding_repo = RuleFindingRepository(db_session)
    findings = await finding_repo.list_current_for_machine(tenant.id, machine.id)
    pressure_findings = [
        f for f in findings if f.finding_type == RuleFindingType.PRESSURE_ABOVE_CONTEXTUAL_BASELINE
    ]
    assert len(pressure_findings) == 1
    assert pressure_findings[0].state == RuleFindingState.ACTIVE


@pytest.mark.asyncio
async def test_finding_recovers_and_resolves_when_condition_clears(
    db_session: AsyncSession,
) -> None:
    tenant, machine, system, circuit, _bearing = await build_machine_with_topology(db_session)
    sensor = await make_topology_sensor(
        db_session, tenant, SensorType.PRESSURE, circuit_id=circuit.id
    )
    now = datetime.now(UTC)
    start = now - timedelta(hours=1)
    await create_active_baseline(
        db_session,
        tenant_id=tenant.id,
        sensor_id=sensor.id,
        machine_id=machine.id,
        measurement_type="PRESSURE",
        strategy=BaselineStrategyType.ROLLING_ASSET_BASELINE,
        context_key="",
        statistics=robust_stats(median=9.0, mad=0.5),
    )

    bad_rows = [
        telemetry_row(
            tenant_id=tenant.id,
            sensor_id=sensor.id,
            machine_id=machine.id,
            circuit_id=circuit.id,
            source_timestamp=t,
            value=25.0,
            measurement_type=SensorType.PRESSURE,
        )
        for t in _times(start, 30)
    ]
    await insert_rows(db_session, bad_rows)
    await set_eligibility(db_session, tenant.id, sensor.id, machine.id, Eligibility.ELIGIBLE)

    engine = RuleEngine(db_session, BASELINE_POLICY, RULES_POLICY)
    await _run_cycles(engine, tenant.id, machine.id, now, (start, now), cycles=3)

    finding_repo = RuleFindingRepository(db_session)
    active = await finding_repo.list_current_for_machine(tenant.id, machine.id)
    assert any(f.state == RuleFindingState.ACTIVE for f in active)

    # Now the pressure recovers to normal — a fresh healthy window.
    later_start = now + timedelta(minutes=1)
    later_end = later_start + timedelta(hours=1)
    good_rows = [
        telemetry_row(
            tenant_id=tenant.id,
            sensor_id=sensor.id,
            machine_id=machine.id,
            circuit_id=circuit.id,
            source_timestamp=t,
            value=9.1,
            measurement_type=SensorType.PRESSURE,
        )
        for t in _times(later_start, 30)
    ]
    await insert_rows(db_session, good_rows)

    await engine.evaluate_machine(
        tenant.id, machine.id, later_end, window_override=(later_start, later_end)
    )
    mid = await finding_repo.list_current_for_machine(tenant.id, machine.id)
    pressure_mid = [
        f for f in mid if f.finding_type == RuleFindingType.PRESSURE_ABOVE_CONTEXTUAL_BASELINE
    ]
    assert len(pressure_mid) == 1
    assert pressure_mid[0].state == RuleFindingState.RECOVERING

    await engine.evaluate_machine(
        tenant.id, machine.id, later_end, window_override=(later_start, later_end)
    )
    after = await finding_repo.list_current_for_machine(tenant.id, machine.id)
    pressure_after = [
        f for f in after if f.finding_type == RuleFindingType.PRESSURE_ABOVE_CONTEXTUAL_BASELINE
    ]
    assert pressure_after == []  # RESOLVED rows are no longer "current"
