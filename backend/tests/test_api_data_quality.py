"""API-level tests for `GET /api/v1/data-quality/sensors` — the fleet-wide sensor-quality
read model added for the Data Quality product rebuild. `GET /issues` alone cannot answer
"show me every evaluated sensor" (a trusted sensor never has an issue row), so this
endpoint is the one the redesigned Data Quality page's main table is built on."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.data_quality.repositories.sensor_quality_state_repository import (
    SensorQualityStateRepository,
)
from app.domain.enums import Eligibility, QualityState, SensorType
from app.domain.models import Tenant
from app.infrastructure.database import Database
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
class SeededSensor:
    tenant: Tenant
    machine_id: uuid.UUID
    sensor_id: uuid.UUID


async def _seed_trusted_sensor(tenant: Tenant | None = None) -> SeededSensor:
    database = Database(get_settings())
    try:
        async with database.session() as session:
            tenant = tenant or await make_tenant(session)
            customer = await make_customer(session, tenant)
            site = await make_site(session, tenant, customer)
            plant = await make_plant(session, tenant, site)
            line = await make_production_line(session, tenant, plant)
            machine = await make_machine(session, tenant, line)
            sensor = await make_sensor(
                session, tenant, sensor_type=SensorType.PRESSURE, machine_id=machine.id
            )
            await SensorQualityStateRepository(session).upsert(
                tenant.id,
                sensor.id,
                machine_id=machine.id,
                quality_state=QualityState.TRUSTED,
                eligibility=Eligibility.ELIGIBLE,
                last_observed_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            await session.commit()
            return SeededSensor(tenant=tenant, machine_id=machine.id, sensor_id=sensor.id)
    finally:
        await database.dispose()


def test_list_fleet_sensor_quality_includes_trusted_sensor(client: TestClient) -> None:
    seeded = asyncio.run(_seed_trusted_sensor())
    headers = {TENANT_HEADER: str(seeded.tenant.id)}

    response = client.get("/api/v1/data-quality/sensors", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    record = body[0]
    assert record["sensor_id"] == str(seeded.sensor_id)
    assert record["state"]["quality_state"] == "TRUSTED"
    assert record["active_issues"] == []
    assert record["expected_reporting_interval_seconds"] == 10.0


def test_list_fleet_sensor_quality_filters_by_machine_id(client: TestClient) -> None:
    seeded_a = asyncio.run(_seed_trusted_sensor())
    seeded_b = asyncio.run(_seed_trusted_sensor(seeded_a.tenant))
    headers = {TENANT_HEADER: str(seeded_a.tenant.id)}

    response = client.get(
        "/api/v1/data-quality/sensors",
        headers=headers,
        params={"machine_id": str(seeded_b.machine_id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert [row["sensor_id"] for row in body] == [str(seeded_b.sensor_id)]


def test_list_fleet_sensor_quality_is_tenant_scoped(client: TestClient) -> None:
    seeded_a = asyncio.run(_seed_trusted_sensor())
    seeded_b = asyncio.run(_seed_trusted_sensor())
    headers_b = {TENANT_HEADER: str(seeded_b.tenant.id)}

    response = client.get("/api/v1/data-quality/sensors", headers=headers_b)

    assert response.status_code == 200
    body = response.json()
    sensor_ids = {row["sensor_id"] for row in body}
    assert str(seeded_b.sensor_id) in sensor_ids
    assert str(seeded_a.sensor_id) not in sensor_ids
