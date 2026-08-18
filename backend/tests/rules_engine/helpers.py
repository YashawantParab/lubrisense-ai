"""Shared test helpers for `tests/rules_engine/` integration tests — builds real
`telemetry`/`sensor_quality_state`/`baseline_profile` rows directly (bypassing the Phase
6/7/8 pipelines, which are out of scope for these tests) so `RuleEngine` can be exercised
against live Postgres the same way `tests/baselines/test_baseline_engine.py` already does.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.baselines.repositories.baseline_profile_repository import BaselineProfileRepository
from app.data_quality.repositories.sensor_quality_state_repository import (
    SensorQualityStateRepository,
)
from app.domain.enums import (
    BaselineMetricKind,
    BaselineState,
    BaselineStrategyType,
    Eligibility,
    QualityState,
    SensorType,
    TelemetryQuality,
)
from app.domain.models import Bearing, Circuit, LubricationSystem, Machine, Sensor, Tenant
from app.repositories.telemetry import TelemetryRepository
from tests.factories import (
    make_bearing,
    make_circuit,
    make_customer,
    make_lubrication_system,
    make_machine,
    make_plant,
    make_production_line,
    make_sensor,
    make_site,
    make_tenant,
)


def telemetry_row(
    *,
    tenant_id: uuid.UUID,
    sensor_id: uuid.UUID,
    machine_id: uuid.UUID | None,
    source_timestamp: datetime,
    value: float | None,
    measurement_type: SensorType,
    unit: str = "bar",
    operating_state: str = "RUNNING_NORMAL_LOAD",
    quality: TelemetryQuality = TelemetryQuality.GOOD,
    bearing_id: uuid.UUID | None = None,
    circuit_id: uuid.UUID | None = None,
    lubrication_system_id: uuid.UUID | None = None,
    sequence_number: int = 1,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "event_id": uuid.uuid4(),
        "schema_version": "1",
        "correlation_id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "site_id": None,
        "plant_id": None,
        "production_line_id": None,
        "machine_id": machine_id,
        "bearing_id": bearing_id,
        "lubrication_system_id": lubrication_system_id,
        "circuit_id": circuit_id,
        "lubrication_point_id": None,
        "sensor_id": sensor_id,
        "measurement_type": measurement_type,
        "value": value,
        "unit": unit,
        "quality": quality,
        "operating_state": operating_state,
        "source_timestamp": source_timestamp,
        "edge_received_timestamp": source_timestamp,
        "edge_emitted_timestamp": None,
        "mqtt_received_timestamp": now,
        "kafka_published_timestamp": now,
        "consumer_received_timestamp": now,
        "sequence_number": sequence_number,
        "gateway_id": "GW-TEST",
        "device_id": "sim-device",
        "firmware_version": None,
        "controller_version": None,
        "source": "synthetic",
        "metadata": {},
        "kafka_partition": 0,
        "kafka_offset": 0,
    }


async def insert_rows(session: AsyncSession, rows: list[dict[str, Any]]) -> None:
    repo = TelemetryRepository(session)
    await repo.batch_insert_idempotent(rows)


async def set_eligibility(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    sensor_id: uuid.UUID,
    machine_id: uuid.UUID | None,
    eligibility: Eligibility,
) -> None:
    repo = SensorQualityStateRepository(session)
    await repo.upsert(
        tenant_id,
        sensor_id,
        machine_id=machine_id,
        quality_state=QualityState.TRUSTED
        if eligibility == Eligibility.ELIGIBLE
        else QualityState.UNUSABLE,
        eligibility=eligibility,
        policy_version="1",
    )


async def create_active_baseline(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    sensor_id: uuid.UUID,
    machine_id: uuid.UUID | None,
    measurement_type: str,
    strategy: BaselineStrategyType,
    context_key: str,
    statistics: dict[str, Any],
    sample_count: int = 100,
    metric_kind: BaselineMetricKind = BaselineMetricKind.STANDARD,
    state: BaselineState = BaselineState.ACTIVE,
) -> Any:
    repo = BaselineProfileRepository(session)
    now = datetime.now(UTC)
    return await repo.create_initial(
        tenant_id=tenant_id,
        sensor_id=sensor_id,
        machine_id=machine_id,
        measurement_type=measurement_type,
        strategy=strategy,
        metric_kind=metric_kind,
        context_key=context_key,
        context={},
        state=state,
        statistics=statistics,
        sample_count=sample_count,
        min_sample_required=10,
        window_start=now,
        window_end=now,
        window_seconds=3600.0,
        config_version="1",
        activated_at=now,
        last_evaluated_at=now,
        refresh_interval_seconds=900.0,
        stale_after_seconds=3600.0,
    )


def robust_stats(median: float, mad: float, **overrides: float) -> dict[str, float]:
    """A minimal but complete `RobustStatistics`-shaped dict — every field
    `app.baselines.domain.statistics.RobustStatistics` requires, defaulted around
    `median` so `compute_deviation` never KeyErrors in a test."""
    base = {
        "count": 100,
        "caution_count": 0,
        "mean": median,
        "stddev": mad if mad > 0 else 1.0,
        "median": median,
        "mad": mad,
        "p05": median - 4 * mad,
        "p25": median - mad,
        "p75": median + mad,
        "p95": median + 4 * mad,
        "min": median - 6 * mad,
        "max": median + 6 * mad,
    }
    base.update(overrides)
    return base


async def build_machine_with_topology(
    session: AsyncSession,
) -> tuple[Tenant, Machine, LubricationSystem, Circuit, Bearing]:
    tenant = await make_tenant(session)
    customer = await make_customer(session, tenant)
    site = await make_site(session, tenant, customer)
    plant = await make_plant(session, tenant, site)
    line = await make_production_line(session, tenant, plant)
    machine = await make_machine(session, tenant, line)
    system = await make_lubrication_system(session, tenant, machine)
    circuit = await make_circuit(session, tenant, system)
    bearing = await make_bearing(session, tenant, machine)
    return tenant, machine, system, circuit, bearing


async def make_topology_sensor(
    session: AsyncSession,
    tenant: Tenant,
    sensor_type: SensorType,
    **attachment: uuid.UUID,
) -> Sensor:
    return await make_sensor(session, tenant, sensor_type=sensor_type, **attachment)
