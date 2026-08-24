"""Integration tests for `EnergyAssessmentService` against live Postgres — mirrors
`tests/baselines/test_baseline_engine.py`'s own "drive the real engine against real
inserted telemetry" convention. Builds no new expected-value algorithm of its own: these
tests exercise the exact same `app.baselines` machinery `tests/baselines/` already tests
directly, from the energy-assessment orchestration layer on top of it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.baselines.config.policy import load_baseline_policy
from app.baselines.services.baseline_engine import BaselineEngine
from app.domain.enums import Eligibility, EnergyAssessmentStatus, QualityState, SensorType
from app.domain.models import Machine, Sensor, Tenant
from app.energy.services.energy_assessment_service import (
    EnergyAssessmentService,
    EnergyMachineNotFoundError,
    EnergyPowerSensorNotFoundError,
)
from tests.baselines.helpers import build_hierarchy, insert_rows, set_eligibility, telemetry_row
from tests.factories import make_tenant

POLICY = load_baseline_policy()


def _times(start: datetime, count: int, step_seconds: float = 5.0) -> list[datetime]:
    return [start + timedelta(seconds=step_seconds * i) for i in range(count)]


async def _seed_power_baseline(
    session: AsyncSession,
    tenant: Tenant,
    machine: Machine,
    sensor: Sensor,
    *,
    value: float,
    now: datetime,
) -> None:
    start = now - timedelta(hours=1)
    rows = [
        telemetry_row(
            tenant_id=tenant.id,
            sensor_id=sensor.id,
            machine_id=machine.id,
            source_timestamp=t,
            value=value,
            measurement_type=SensorType.MACHINE_POWER,
        )
        for t in _times(start, 40)
    ]
    await insert_rows(session, rows)
    await set_eligibility(session, tenant.id, sensor.id, machine.id, Eligibility.ELIGIBLE)

    engine = BaselineEngine(session, POLICY)
    for _ in range(3):
        await engine.refresh_sensor(tenant.id, sensor, now, window_override=(start, now))
    await session.commit()


@pytest.mark.asyncio
async def test_actual_at_baseline_is_within_expected_range(db_session: AsyncSession) -> None:
    tenant, machine, sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    now = datetime.now(UTC)
    await _seed_power_baseline(db_session, tenant, machine, sensor, value=50.0, now=now)
    # One more reading right at the baseline center, as the "latest" the service reads.
    await insert_rows(
        db_session,
        [
            telemetry_row(
                tenant_id=tenant.id,
                sensor_id=sensor.id,
                machine_id=machine.id,
                source_timestamp=now,
                value=50.0,
                measurement_type=SensorType.MACHINE_POWER,
            )
        ],
    )
    await db_session.commit()

    service = EnergyAssessmentService(db_session, POLICY)
    result = await service.assess_machine(tenant.id, machine.id)

    assert result.status == EnergyAssessmentStatus.WITHIN_EXPECTED_RANGE
    assert result.actual_power_kw == 50.0
    assert result.expected_power_kw is not None
    assert result.residual_kw is not None
    assert abs(result.residual_kw) < 1.0
    assert result.data_quality_state == QualityState.TRUSTED
    assert result.power_sensor_id == sensor.id


@pytest.mark.asyncio
async def test_actual_far_above_baseline_is_elevated_energy_demand(
    db_session: AsyncSession,
) -> None:
    tenant, machine, sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    now = datetime.now(UTC)
    await _seed_power_baseline(db_session, tenant, machine, sensor, value=50.0, now=now)
    await insert_rows(
        db_session,
        [
            telemetry_row(
                tenant_id=tenant.id,
                sensor_id=sensor.id,
                machine_id=machine.id,
                source_timestamp=now,
                value=90.0,
                measurement_type=SensorType.MACHINE_POWER,
            )
        ],
    )
    await db_session.commit()

    service = EnergyAssessmentService(db_session, POLICY)
    result = await service.assess_machine(tenant.id, machine.id)

    assert result.status == EnergyAssessmentStatus.ELEVATED_ENERGY_DEMAND
    assert result.residual_kw is not None
    assert result.residual_kw > 0
    assert result.residual_pct is not None
    assert result.residual_pct > 0


@pytest.mark.asyncio
async def test_no_power_sensor_raises(db_session: AsyncSession) -> None:
    tenant, machine, _sensor = await build_hierarchy(db_session, sensor_type=SensorType.PRESSURE)
    await db_session.commit()

    service = EnergyAssessmentService(db_session, POLICY)
    with pytest.raises(EnergyPowerSensorNotFoundError):
        await service.assess_machine(tenant.id, machine.id)


@pytest.mark.asyncio
async def test_machine_not_found_raises(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    await db_session.commit()

    service = EnergyAssessmentService(db_session, POLICY)
    with pytest.raises(EnergyMachineNotFoundError):
        await service.assess_machine(tenant.id, uuid.uuid4())


@pytest.mark.asyncio
async def test_sensor_with_no_telemetry_is_insufficient_data(db_session: AsyncSession) -> None:
    tenant, machine, _sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    await db_session.commit()

    service = EnergyAssessmentService(db_session, POLICY)
    result = await service.assess_machine(tenant.id, machine.id)

    assert result.status == EnergyAssessmentStatus.INSUFFICIENT_DATA
    assert result.actual_power_kw is None
    assert result.expected_power_kw is None
    assert result.residual_kw is None


@pytest.mark.asyncio
async def test_telemetry_without_a_built_baseline_is_insufficient_baseline(
    db_session: AsyncSession,
) -> None:
    tenant, machine, sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    now = datetime.now(UTC)
    await insert_rows(
        db_session,
        [
            telemetry_row(
                tenant_id=tenant.id,
                sensor_id=sensor.id,
                machine_id=machine.id,
                source_timestamp=now,
                value=50.0,
                measurement_type=SensorType.MACHINE_POWER,
            )
        ],
    )
    await set_eligibility(db_session, tenant.id, sensor.id, machine.id, Eligibility.ELIGIBLE)
    await db_session.commit()

    service = EnergyAssessmentService(db_session, POLICY)
    result = await service.assess_machine(tenant.id, machine.id)

    assert result.status == EnergyAssessmentStatus.INSUFFICIENT_BASELINE
    assert result.actual_power_kw == 50.0
    assert result.expected_power_kw is None
    assert result.residual_kw is None


@pytest.mark.asyncio
async def test_unusable_power_sensor_is_data_quality_limited(db_session: AsyncSession) -> None:
    tenant, machine, sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    now = datetime.now(UTC)
    await _seed_power_baseline(db_session, tenant, machine, sensor, value=50.0, now=now)
    await insert_rows(
        db_session,
        [
            telemetry_row(
                tenant_id=tenant.id,
                sensor_id=sensor.id,
                machine_id=machine.id,
                source_timestamp=now,
                value=90.0,
                measurement_type=SensorType.MACHINE_POWER,
            )
        ],
    )
    await set_eligibility(db_session, tenant.id, sensor.id, machine.id, Eligibility.INELIGIBLE)
    await db_session.commit()

    service = EnergyAssessmentService(db_session, POLICY)
    result = await service.assess_machine(tenant.id, machine.id)

    assert result.status == EnergyAssessmentStatus.DATA_QUALITY_LIMITED
    assert result.data_quality_state == QualityState.UNUSABLE
    # An untrusted reading is never surfaced as if it were real evidence.
    assert result.actual_power_kw is None
    assert result.expected_power_kw is None


@pytest.mark.asyncio
async def test_tenant_isolation(db_session: AsyncSession) -> None:
    """A real `MachineRepository.get` tenant_id filter, not a special case in
    `EnergyAssessmentService` itself — tenant B must never be able to assess tenant A's
    machine just by knowing its id."""
    tenant_a, machine_a, sensor_a = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    now = datetime.now(UTC)
    await _seed_power_baseline(db_session, tenant_a, machine_a, sensor_a, value=50.0, now=now)

    tenant_b = await make_tenant(db_session)
    await db_session.commit()

    service = EnergyAssessmentService(db_session, POLICY)
    with pytest.raises(EnergyMachineNotFoundError):
        await service.assess_machine(tenant_b.id, machine_a.id)
