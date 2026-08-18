"""Shared test helpers for `tests/baselines/` integration tests — builds real `telemetry`
rows and `sensor_quality_state` rows directly (bypassing the Phase 6/7 pipeline, which is
out of scope for these tests) so `BaselineEngine` can be exercised against live Postgres
the same way `tests/test_telemetry_repository.py` already does.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.data_quality.repositories.sensor_quality_state_repository import (
    SensorQualityStateRepository,
)
from app.domain.enums import Eligibility, QualityState, SensorType, TelemetryQuality
from app.domain.models import Machine, Sensor, Tenant
from app.repositories.telemetry import TelemetryRepository
from tests.factories import (
    make_customer,
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
    measurement_type: SensorType = SensorType.PRESSURE,
    operating_state: str = "RUNNING_NORMAL_LOAD",
    quality: TelemetryQuality = TelemetryQuality.GOOD,
    firmware_version: str | None = None,
    controller_version: str | None = None,
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
        "bearing_id": None,
        "lubrication_system_id": None,
        "circuit_id": None,
        "lubrication_point_id": None,
        "sensor_id": sensor_id,
        "measurement_type": measurement_type,
        "value": value,
        "unit": "bar",
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
        "firmware_version": firmware_version,
        "controller_version": controller_version,
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
    """Directly upserts `sensor_quality_state` — simulates the Phase 7 worker's judgment
    without needing the real quality engine/rules in these baseline-focused tests."""
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


async def build_hierarchy(
    session: AsyncSession, *, sensor_type: SensorType = SensorType.PRESSURE
) -> tuple[Tenant, Machine, Sensor]:
    tenant = await make_tenant(session)
    customer = await make_customer(session, tenant)
    site = await make_site(session, tenant, customer)
    plant = await make_plant(session, tenant, site)
    line = await make_production_line(session, tenant, plant)
    machine = await make_machine(session, tenant, line)
    sensor = await make_sensor(session, tenant, sensor_type=sensor_type, machine_id=machine.id)
    return tenant, machine, sensor
