"""`TelemetryRepository` tests against live TimescaleDB (idempotency, time-range/latest
queries)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import SensorType, TelemetryQuality
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


def _row(
    *,
    tenant_id,
    sensor_id,
    machine_id,
    source_timestamp,
    value,
    event_id=None,
    measurement_type=SensorType.PRESSURE,
):  # type: ignore[no-untyped-def]
    now = datetime.now(UTC)
    return {
        "event_id": event_id or uuid.uuid4(),
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
        "quality": TelemetryQuality.GOOD,
        "operating_state": "RUNNING_NORMAL_LOAD",
        "source_timestamp": source_timestamp,
        "edge_received_timestamp": source_timestamp,
        "edge_emitted_timestamp": None,
        "mqtt_received_timestamp": now,
        "kafka_published_timestamp": now,
        "consumer_received_timestamp": now,
        "sequence_number": 1,
        "gateway_id": "GW-TEST",
        "device_id": "sim-device",
        "firmware_version": None,
        "controller_version": None,
        "source": "synthetic",
        "metadata": {},
        "kafka_partition": 0,
        "kafka_offset": 0,
    }


async def _hierarchy(db_session: AsyncSession):  # type: ignore[no-untyped-def]
    tenant = await make_tenant(db_session)
    customer = await make_customer(db_session, tenant)
    site = await make_site(db_session, tenant, customer)
    plant = await make_plant(db_session, tenant, site)
    line = await make_production_line(db_session, tenant, plant)
    machine = await make_machine(db_session, tenant, line)
    sensor = await make_sensor(db_session, tenant, machine_id=machine.id)
    return tenant, machine, sensor


@pytest.mark.asyncio
async def test_batch_insert_idempotent_suppresses_duplicates(db_session: AsyncSession) -> None:
    tenant, machine, sensor = await _hierarchy(db_session)
    repo = TelemetryRepository(db_session)
    now = datetime.now(UTC)
    event_id = uuid.uuid4()
    row = _row(
        tenant_id=tenant.id,
        sensor_id=sensor.id,
        machine_id=machine.id,
        source_timestamp=now,
        value=1.0,
        event_id=event_id,
    )

    first = await repo.batch_insert_idempotent([row])
    second = await repo.batch_insert_idempotent([row])

    assert first == 1
    assert second == 0

    latest = await repo.get_latest_by_sensor(tenant.id, sensor.id)
    assert latest is not None
    assert latest.event_id == event_id


@pytest.mark.asyncio
async def test_batch_insert_mixed_new_and_duplicate(db_session: AsyncSession) -> None:
    tenant, machine, sensor = await _hierarchy(db_session)
    repo = TelemetryRepository(db_session)
    now = datetime.now(UTC)
    existing = _row(
        tenant_id=tenant.id,
        sensor_id=sensor.id,
        machine_id=machine.id,
        source_timestamp=now,
        value=1.0,
    )
    await repo.batch_insert_idempotent([existing])

    new_row = _row(
        tenant_id=tenant.id,
        sensor_id=sensor.id,
        machine_id=machine.id,
        source_timestamp=now + timedelta(seconds=1),
        value=2.0,
    )
    inserted = await repo.batch_insert_idempotent([existing, new_row])
    assert inserted == 1


@pytest.mark.asyncio
async def test_get_by_sensor_time_range_filters_and_orders_desc(db_session: AsyncSession) -> None:
    tenant, machine, sensor = await _hierarchy(db_session)
    repo = TelemetryRepository(db_session)
    base = datetime.now(UTC)
    rows = [
        _row(
            tenant_id=tenant.id,
            sensor_id=sensor.id,
            machine_id=machine.id,
            source_timestamp=base + timedelta(minutes=i),
            value=float(i),
        )
        for i in range(5)
    ]
    await repo.batch_insert_idempotent(rows)

    results = await repo.get_by_sensor_time_range(
        tenant.id, sensor.id, start=base + timedelta(minutes=1), end=base + timedelta(minutes=3)
    )
    values = sorted(r.value for r in results)
    assert values == [1.0, 2.0, 3.0]
    assert results[0].source_timestamp >= results[-1].source_timestamp  # DESC order


@pytest.mark.asyncio
async def test_get_by_machine_time_range_scopes_to_machine(db_session: AsyncSession) -> None:
    tenant, machine, sensor = await _hierarchy(db_session)
    other_sensor = await make_sensor(db_session, tenant, machine_id=machine.id)
    repo = TelemetryRepository(db_session)
    now = datetime.now(UTC)
    await repo.batch_insert_idempotent(
        [
            _row(
                tenant_id=tenant.id,
                sensor_id=sensor.id,
                machine_id=machine.id,
                source_timestamp=now,
                value=1.0,
            ),
            _row(
                tenant_id=tenant.id,
                sensor_id=other_sensor.id,
                machine_id=machine.id,
                source_timestamp=now + timedelta(seconds=1),
                value=2.0,
            ),
        ]
    )

    results = await repo.get_by_machine_time_range(tenant.id, machine.id, start=None, end=None)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_get_by_sensor_time_range_measurement_type_filter(db_session: AsyncSession) -> None:
    tenant, machine, sensor = await _hierarchy(db_session)
    repo = TelemetryRepository(db_session)
    now = datetime.now(UTC)
    await repo.batch_insert_idempotent(
        [
            _row(
                tenant_id=tenant.id,
                sensor_id=sensor.id,
                machine_id=machine.id,
                source_timestamp=now,
                value=1.0,
                measurement_type=SensorType.PRESSURE,
            ),
            _row(
                tenant_id=tenant.id,
                sensor_id=sensor.id,
                machine_id=machine.id,
                source_timestamp=now + timedelta(seconds=1),
                value=2.0,
                measurement_type=SensorType.RPM,
            ),
        ]
    )

    results = await repo.get_by_sensor_time_range(
        tenant.id, sensor.id, start=None, end=None, measurement_type=SensorType.RPM
    )
    assert len(results) == 1
    assert results[0].measurement_type == SensorType.RPM


@pytest.mark.asyncio
async def test_latest_by_sensor_returns_none_when_no_readings(db_session: AsyncSession) -> None:
    tenant, machine, sensor = await _hierarchy(db_session)
    repo = TelemetryRepository(db_session)
    result = await repo.get_latest_by_sensor(tenant.id, sensor.id)
    assert result is None


@pytest.mark.asyncio
async def test_empty_batch_insert_is_a_noop(db_session: AsyncSession) -> None:
    repo = TelemetryRepository(db_session)
    assert await repo.batch_insert_idempotent([]) == 0
