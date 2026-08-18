"""API-level tests for `/api/v1/telemetry/*` — real HTTP requests via `TestClient` against
real Postgres, seeded with committed rows (ingestion is MQTT/Kafka-only by design, so there
is no ingestion endpoint to seed through — see docs/TELEMETRY_PIPELINE.md)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.domain.enums import SensorType, TelemetryQuality
from app.domain.models import Machine, Sensor, Tenant
from app.infrastructure.database import Database
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

TENANT_HEADER = "X-Tenant-ID"


@dataclass(frozen=True)
class SeededTelemetry:
    tenant: Tenant
    machine: Machine
    sensor: Sensor
    event_id: uuid.UUID


@pytest_asyncio.fixture
async def seeded_telemetry() -> AsyncIterator[SeededTelemetry]:
    database = Database(get_settings())
    try:
        async with database.session() as session:
            tenant = await make_tenant(session)
            customer = await make_customer(session, tenant)
            site = await make_site(session, tenant, customer)
            plant = await make_plant(session, tenant, site)
            line = await make_production_line(session, tenant, plant)
            machine = await make_machine(session, tenant, line)
            sensor = await make_sensor(session, tenant, machine_id=machine.id)

            now = datetime.now(UTC)
            event_id = uuid.uuid4()
            repo = TelemetryRepository(session)
            await repo.batch_insert_idempotent(
                [
                    {
                        "event_id": event_id,
                        "schema_version": "1",
                        "correlation_id": str(uuid.uuid4()),
                        "tenant_id": tenant.id,
                        "site_id": site.id,
                        "plant_id": plant.id,
                        "production_line_id": line.id,
                        "machine_id": machine.id,
                        "bearing_id": None,
                        "lubrication_system_id": None,
                        "circuit_id": None,
                        "lubrication_point_id": None,
                        "sensor_id": sensor.id,
                        "measurement_type": SensorType.PRESSURE,
                        "value": 4.5,
                        "unit": "bar",
                        "quality": TelemetryQuality.GOOD,
                        "operating_state": "RUNNING_NORMAL_LOAD",
                        "source_timestamp": now - timedelta(minutes=1),
                        "edge_received_timestamp": now - timedelta(minutes=1),
                        "edge_emitted_timestamp": None,
                        "mqtt_received_timestamp": now,
                        "kafka_published_timestamp": now,
                        "consumer_received_timestamp": now,
                        "sequence_number": 1,
                        "gateway_id": "GW-API-TEST",
                        "device_id": "sim-device",
                        "firmware_version": None,
                        "controller_version": None,
                        "source": "synthetic",
                        "metadata": {},
                        "kafka_partition": 0,
                        "kafka_offset": 0,
                    }
                ]
            )
            await session.commit()
            yield SeededTelemetry(tenant=tenant, machine=machine, sensor=sensor, event_id=event_id)
    finally:
        await database.dispose()


def test_sensor_telemetry_requires_tenant_header(
    client: TestClient, seeded_telemetry: SeededTelemetry
) -> None:
    response = client.get(f"/api/v1/telemetry/sensors/{seeded_telemetry.sensor.id}")
    assert response.status_code == 400


def test_sensor_telemetry_returns_seeded_row(
    client: TestClient, seeded_telemetry: SeededTelemetry
) -> None:
    headers = {TENANT_HEADER: str(seeded_telemetry.tenant.id)}
    response = client.get(
        f"/api/v1/telemetry/sensors/{seeded_telemetry.sensor.id}", headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["event_id"] == str(seeded_telemetry.event_id)
    assert body[0]["value"] == 4.5
    assert body[0]["quality"] == "GOOD"


def test_sensor_telemetry_unknown_sensor_is_404(
    client: TestClient, seeded_telemetry: SeededTelemetry
) -> None:
    headers = {TENANT_HEADER: str(seeded_telemetry.tenant.id)}
    response = client.get(f"/api/v1/telemetry/sensors/{uuid.uuid4()}", headers=headers)
    assert response.status_code == 404
    assert response.json()["code"] == "SENSOR_NOT_FOUND"


def test_sensor_latest_telemetry(client: TestClient, seeded_telemetry: SeededTelemetry) -> None:
    headers = {TENANT_HEADER: str(seeded_telemetry.tenant.id)}
    response = client.get(
        f"/api/v1/telemetry/sensors/{seeded_telemetry.sensor.id}/latest", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["event_id"] == str(seeded_telemetry.event_id)


def test_machine_telemetry_returns_seeded_row(
    client: TestClient, seeded_telemetry: SeededTelemetry
) -> None:
    headers = {TENANT_HEADER: str(seeded_telemetry.tenant.id)}
    response = client.get(
        f"/api/v1/telemetry/machines/{seeded_telemetry.machine.id}", headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["machine_id"] == str(seeded_telemetry.machine.id)


def test_machine_telemetry_unknown_machine_is_404(
    client: TestClient, seeded_telemetry: SeededTelemetry
) -> None:
    headers = {TENANT_HEADER: str(seeded_telemetry.tenant.id)}
    response = client.get(f"/api/v1/telemetry/machines/{uuid.uuid4()}", headers=headers)
    assert response.status_code == 404
    assert response.json()["code"] == "MACHINE_NOT_FOUND"


def test_sensor_telemetry_time_range_excludes_out_of_range(
    client: TestClient, seeded_telemetry: SeededTelemetry
) -> None:
    headers = {TENANT_HEADER: str(seeded_telemetry.tenant.id)}
    future_start = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    response = client.get(
        f"/api/v1/telemetry/sensors/{seeded_telemetry.sensor.id}",
        headers=headers,
        params={"start": future_start},
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_cross_tenant_sensor_telemetry_is_404(
    client: TestClient, seeded_telemetry: SeededTelemetry
) -> None:
    """A different (real) tenant querying another tenant's sensor must not see it."""
    database = Database(get_settings())
    try:
        async with database.session() as session:
            other_tenant = await make_tenant(session)
            await session.commit()
    finally:
        await database.dispose()

    headers = {TENANT_HEADER: str(other_tenant.id)}
    response = client.get(
        f"/api/v1/telemetry/sensors/{seeded_telemetry.sensor.id}", headers=headers
    )
    assert response.status_code == 404
