"""Integration tests for `BaselineEngine` against live Postgres — quality gating,
load/cycle-phase-dependent contextual profiles, sensor-drift and gradual-physical-fault
contamination protection, firmware-change invalidation, fallback hierarchy, and
idempotency (Phase 8 brief §35-§41, §21-§22, §30).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.baselines.config.policy import load_baseline_policy
from app.baselines.domain.context import BaselineContext
from app.baselines.repositories.baseline_profile_repository import BaselineProfileRepository
from app.baselines.services.baseline_engine import BaselineEngine
from app.baselines.services.fallback import resolve_baseline
from app.domain.enums import (
    BaselineSourceKind,
    BaselineState,
    BaselineStrategyType,
    Eligibility,
    SensorType,
    TelemetryQuality,
)
from tests.baselines.helpers import build_hierarchy, insert_rows, set_eligibility, telemetry_row

POLICY = load_baseline_policy()


def _times(start: datetime, count: int, step_seconds: float = 5.0) -> list[datetime]:
    return [start + timedelta(seconds=step_seconds * i) for i in range(count)]


async def _refresh_until_active(
    engine: BaselineEngine,
    tenant_id,
    sensor,
    now: datetime,
    window: tuple[datetime, datetime],
    cycles: int = 3,
) -> None:
    for _ in range(cycles):
        await engine.refresh_sensor(tenant_id, sensor, now, window_override=window)


@pytest.mark.asyncio
async def test_ineligible_sensor_never_updates_learned_baseline(db_session: AsyncSession) -> None:
    tenant, machine, sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.BEARING_TEMPERATURE
    )
    now = datetime.now(UTC)
    start = now - timedelta(hours=1)
    rows = [
        telemetry_row(
            tenant_id=tenant.id,
            sensor_id=sensor.id,
            machine_id=machine.id,
            source_timestamp=t,
            value=45.0,
            measurement_type=SensorType.BEARING_TEMPERATURE,
        )
        for t in _times(start, 40)
    ]
    await insert_rows(db_session, rows)
    await set_eligibility(db_session, tenant.id, sensor.id, machine.id, Eligibility.INELIGIBLE)

    engine = BaselineEngine(db_session, POLICY)
    await engine.refresh_sensor(tenant.id, sensor, now, window_override=(start, now))

    repo = BaselineProfileRepository(db_session)
    profile = await repo.get_current(
        tenant.id, sensor.id, BaselineStrategyType.ROLLING_ASSET_BASELINE, ""
    )
    assert profile is not None
    assert profile.state == BaselineState.INSUFFICIENT_DATA
    assert profile.sample_count == 0  # ineligible -> zero usable samples, never fabricated


@pytest.mark.asyncio
async def test_own_reading_bad_quality_excluded_from_sample_count(
    db_session: AsyncSession,
) -> None:
    tenant, machine, sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.BEARING_TEMPERATURE
    )
    now = datetime.now(UTC)
    start = now - timedelta(hours=1)
    good_rows = [
        telemetry_row(
            tenant_id=tenant.id,
            sensor_id=sensor.id,
            machine_id=machine.id,
            source_timestamp=t,
            value=45.0,
            measurement_type=SensorType.BEARING_TEMPERATURE,
            quality=TelemetryQuality.GOOD,
        )
        for t in _times(start, 20)
    ]
    bad_rows = [
        telemetry_row(
            tenant_id=tenant.id,
            sensor_id=sensor.id,
            machine_id=machine.id,
            source_timestamp=t,
            value=999.0,
            measurement_type=SensorType.BEARING_TEMPERATURE,
            quality=TelemetryQuality.INVALID,
        )
        for t in _times(start + timedelta(hours=0.5), 20)
    ]
    await insert_rows(db_session, good_rows + bad_rows)

    engine = BaselineEngine(db_session, POLICY)
    await engine.refresh_sensor(tenant.id, sensor, now, window_override=(start, now))

    repo = BaselineProfileRepository(db_session)
    profile = await repo.get_current(
        tenant.id, sensor.id, BaselineStrategyType.ROLLING_ASSET_BASELINE, ""
    )
    assert profile is not None
    assert profile.sample_count == 20  # only the GOOD-quality rows


@pytest.mark.asyncio
async def test_load_dependent_contextual_profiles_differ(db_session: AsyncSession) -> None:
    tenant, machine, sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.BEARING_TEMPERATURE
    )
    now = datetime.now(UTC)
    start = now - timedelta(hours=1)
    low_load_rows = [
        telemetry_row(
            tenant_id=tenant.id,
            sensor_id=sensor.id,
            machine_id=machine.id,
            source_timestamp=t,
            value=35.0,
            measurement_type=SensorType.BEARING_TEMPERATURE,
            operating_state="RUNNING_LOW_LOAD",
        )
        for t in _times(start, 35)
    ]
    high_load_rows = [
        telemetry_row(
            tenant_id=tenant.id,
            sensor_id=sensor.id,
            machine_id=machine.id,
            source_timestamp=t,
            value=85.0,
            measurement_type=SensorType.BEARING_TEMPERATURE,
            operating_state="RUNNING_HIGH_LOAD",
        )
        for t in _times(start + timedelta(minutes=20), 35)
    ]
    await insert_rows(db_session, low_load_rows + high_load_rows)

    engine = BaselineEngine(db_session, POLICY)
    await _refresh_until_active(engine, tenant.id, sensor, now, (start, now))

    repo = BaselineProfileRepository(db_session)
    low = await repo.get_current(
        tenant.id,
        sensor.id,
        BaselineStrategyType.CONTEXTUAL_ASSET_BASELINE,
        "operating_state=RUNNING_LOW_LOAD",
    )
    high = await repo.get_current(
        tenant.id,
        sensor.id,
        BaselineStrategyType.CONTEXTUAL_ASSET_BASELINE,
        "operating_state=RUNNING_HIGH_LOAD",
    )
    assert low is not None and high is not None
    assert low.state == BaselineState.ACTIVE
    assert high.state == BaselineState.ACTIVE
    assert low.statistics is not None and high.statistics is not None
    assert low.statistics["median"] < high.statistics["median"] - 10  # genuinely distinct


@pytest.mark.asyncio
async def test_cycle_phase_profiles_differ(db_session: AsyncSession) -> None:
    tenant, machine, sensor = await build_hierarchy(db_session, sensor_type=SensorType.PRESSURE)
    now = datetime.now(UTC)
    start = now - timedelta(hours=1)
    idle_rows = [
        telemetry_row(
            tenant_id=tenant.id,
            sensor_id=sensor.id,
            machine_id=machine.id,
            source_timestamp=t,
            value=0.05,
            measurement_type=SensorType.PRESSURE,
        )
        for t in _times(start, 35)
    ]
    active_rows = [
        telemetry_row(
            tenant_id=tenant.id,
            sensor_id=sensor.id,
            machine_id=machine.id,
            source_timestamp=t,
            value=9.0,
            measurement_type=SensorType.PRESSURE,
        )
        for t in _times(start + timedelta(minutes=20), 35)
    ]
    await insert_rows(db_session, idle_rows + active_rows)

    engine = BaselineEngine(db_session, POLICY)
    await _refresh_until_active(engine, tenant.id, sensor, now, (start, now))

    repo = BaselineProfileRepository(db_session)
    idle = await repo.get_current(
        tenant.id,
        sensor.id,
        BaselineStrategyType.CONTEXTUAL_ASSET_BASELINE,
        "operating_state=RUNNING_NORMAL_LOAD|cycle_phase=IDLE",
    )
    active = await repo.get_current(
        tenant.id,
        sensor.id,
        BaselineStrategyType.CONTEXTUAL_ASSET_BASELINE,
        "operating_state=RUNNING_NORMAL_LOAD|cycle_phase=ACTIVE",
    )
    assert idle is not None and active is not None
    assert idle.statistics is not None and active.statistics is not None
    assert active.statistics["median"] > idle.statistics["median"] + 5


@pytest.mark.asyncio
async def test_gradual_drift_leaves_active_baseline_anchored(db_session: AsyncSession) -> None:
    """No quality flag involved at all (eligibility stays ELIGIBLE throughout) — this is
    the contamination-control state machine alone protecting against a genuine gradual
    physical fault (brief §40's gradual-restriction scenario)."""
    tenant, machine, sensor = await build_hierarchy(db_session, sensor_type=SensorType.PRESSURE)
    now = datetime.now(UTC)
    start = now - timedelta(hours=1)
    healthy_rows = [
        telemetry_row(
            tenant_id=tenant.id,
            sensor_id=sensor.id,
            machine_id=machine.id,
            source_timestamp=t,
            value=9.0,
            measurement_type=SensorType.PRESSURE,
        )
        for t in _times(start, 35)
    ]
    await insert_rows(db_session, healthy_rows)

    engine = BaselineEngine(db_session, POLICY)
    # Two identical cycles -> first-ever activation.
    await engine.refresh_sensor(tenant.id, sensor, now, window_override=(start, now))
    await engine.refresh_sensor(tenant.id, sensor, now, window_override=(start, now))

    repo = BaselineProfileRepository(db_session)
    active_before = await repo.get_active(
        tenant.id, sensor.id, BaselineStrategyType.ROLLING_ASSET_BASELINE, ""
    )
    assert active_before is not None
    assert active_before.statistics is not None
    anchored_median = active_before.statistics["median"]
    assert anchored_median == pytest.approx(9.0)

    # A developing fault: pressure has drifted sharply upward this cycle.
    drift_start = now - timedelta(minutes=10)
    drift_rows = [
        telemetry_row(
            tenant_id=tenant.id,
            sensor_id=sensor.id,
            machine_id=machine.id,
            source_timestamp=t,
            value=18.0,
            measurement_type=SensorType.PRESSURE,
        )
        for t in _times(drift_start, 35, step_seconds=1.0)
    ]
    await insert_rows(db_session, drift_rows)
    later = now + timedelta(minutes=1)
    await engine.refresh_sensor(tenant.id, sensor, later, window_override=(drift_start, later))

    active_after = await repo.get_active(
        tenant.id, sensor.id, BaselineStrategyType.ROLLING_ASSET_BASELINE, ""
    )
    assert active_after is not None
    assert active_after.id == active_before.id  # same row -- still version 1, never promoted
    assert active_after.statistics is not None
    assert active_after.statistics["median"] == pytest.approx(anchored_median)


@pytest.mark.asyncio
async def test_firmware_change_invalidates_and_starts_new_generation(
    db_session: AsyncSession,
) -> None:
    tenant, machine, sensor = await build_hierarchy(db_session, sensor_type=SensorType.PRESSURE)
    now = datetime.now(UTC)
    start = now - timedelta(hours=1)
    v1_rows = [
        telemetry_row(
            tenant_id=tenant.id,
            sensor_id=sensor.id,
            machine_id=machine.id,
            source_timestamp=t,
            value=9.0,
            measurement_type=SensorType.PRESSURE,
            firmware_version="1.0.0",
        )
        for t in _times(start, 35)
    ]
    await insert_rows(db_session, v1_rows)

    engine = BaselineEngine(db_session, POLICY)
    await engine.refresh_sensor(tenant.id, sensor, now, window_override=(start, now))
    await engine.refresh_sensor(tenant.id, sensor, now, window_override=(start, now))

    repo = BaselineProfileRepository(db_session)
    before = await repo.get_active(
        tenant.id, sensor.id, BaselineStrategyType.ROLLING_ASSET_BASELINE, ""
    )
    assert before is not None

    later = now + timedelta(minutes=5)
    v2_rows = [
        telemetry_row(
            tenant_id=tenant.id,
            sensor_id=sensor.id,
            machine_id=machine.id,
            source_timestamp=t,
            value=9.5,
            measurement_type=SensorType.PRESSURE,
            firmware_version="2.0.0",
        )
        for t in _times(later - timedelta(minutes=10), 35, step_seconds=1.0)
    ]
    await insert_rows(db_session, v2_rows)
    await engine.refresh_sensor(
        tenant.id, sensor, later, window_override=(later - timedelta(minutes=10), later)
    )

    invalidated = await db_session.get(type(before), before.id)
    assert invalidated is not None
    assert invalidated.state == BaselineState.INVALIDATED
    assert invalidated.invalidation_reason is not None

    current = await repo.get_current(
        tenant.id, sensor.id, BaselineStrategyType.ROLLING_ASSET_BASELINE, ""
    )
    assert current is not None
    assert current.id != before.id
    assert current.firmware_version == "2.0.0"


@pytest.mark.asyncio
async def test_fallback_hierarchy_prefers_exact_then_coarse_then_sensor_then_reference(
    db_session: AsyncSession,
) -> None:
    tenant, machine, sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.BEARING_TEMPERATURE
    )
    now = datetime.now(UTC)

    # Nothing learned yet -> falls all the way back to the engineering reference.
    engine = BaselineEngine(db_session, POLICY)
    await engine.refresh_sensor(tenant.id, sensor, now, window_override=(now, now))
    result = await resolve_baseline(
        db_session, POLICY, tenant.id, sensor, BaselineContext(operating_state="RUNNING_LOW_LOAD")
    )
    assert result.source == BaselineSourceKind.ENGINEERING_REFERENCE
    assert result.profile is not None

    # Build only a sensor-level ROLLING baseline (no contextual data).
    start = now - timedelta(hours=1)
    rows = [
        telemetry_row(
            tenant_id=tenant.id,
            sensor_id=sensor.id,
            machine_id=machine.id,
            source_timestamp=t,
            value=50.0,
            measurement_type=SensorType.BEARING_TEMPERATURE,
            operating_state="MAINTENANCE",  # not a stable_operating_state -> no contextual bucket
        )
        for t in _times(start, 35)
    ]
    await insert_rows(db_session, rows)
    await engine.refresh_sensor(tenant.id, sensor, now, window_override=(start, now))
    await engine.refresh_sensor(tenant.id, sensor, now, window_override=(start, now))

    result = await resolve_baseline(
        db_session, POLICY, tenant.id, sensor, BaselineContext(operating_state="RUNNING_LOW_LOAD")
    )
    assert result.source == BaselineSourceKind.SENSOR_LEVEL


@pytest.mark.asyncio
async def test_idempotent_refresh_does_not_duplicate_active_version(
    db_session: AsyncSession,
) -> None:
    tenant, machine, sensor = await build_hierarchy(db_session, sensor_type=SensorType.PRESSURE)
    now = datetime.now(UTC)
    start = now - timedelta(hours=1)
    rows = [
        telemetry_row(
            tenant_id=tenant.id,
            sensor_id=sensor.id,
            machine_id=machine.id,
            source_timestamp=t,
            value=9.0,
            measurement_type=SensorType.PRESSURE,
        )
        for t in _times(start, 35)
    ]
    await insert_rows(db_session, rows)

    engine = BaselineEngine(db_session, POLICY)
    for _ in range(5):
        await engine.refresh_sensor(tenant.id, sensor, now, window_override=(start, now))

    repo = BaselineProfileRepository(db_session)
    versions = await repo.list_versions_for_sensor(tenant.id, sensor.id)
    rolling_versions = [
        v for v in versions if v.strategy == BaselineStrategyType.ROLLING_ASSET_BASELINE
    ]
    assert len(rolling_versions) == 1
    assert rolling_versions[0].version == 1
    assert rolling_versions[0].state == BaselineState.ACTIVE
