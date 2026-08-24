"""API-level tests for `/api/v1/energy/*` — real HTTP requests via `TestClient` against
real Postgres, seeded by running the real `BaselineEngine` against committed telemetry
(mirrors `tests/test_api_baselines.py`'s committed-fixture convention)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from fastapi.testclient import TestClient

from app.baselines.config.policy import load_baseline_policy
from app.baselines.services.baseline_engine import BaselineEngine
from app.core.config import get_settings
from app.domain.enums import SensorType
from app.domain.models import Machine, Sensor, Tenant
from app.infrastructure.database import Database
from tests.baselines.helpers import insert_rows, telemetry_row
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
class SeededEnergyAssessment:
    tenant: Tenant
    machine: Machine
    sensor: Sensor


@pytest_asyncio.fixture
async def seeded_energy_machine() -> AsyncIterator[SeededEnergyAssessment]:
    database = Database(get_settings())
    try:
        async with database.session() as session:
            tenant = await make_tenant(session)
            customer = await make_customer(session, tenant)
            site = await make_site(session, tenant, customer)
            plant = await make_plant(session, tenant, site)
            line = await make_production_line(session, tenant, plant)
            machine = await make_machine(session, tenant, line)
            sensor = await make_sensor(
                session, tenant, sensor_type=SensorType.MACHINE_POWER, machine_id=machine.id
            )

            now = datetime.now(UTC)
            start = now - timedelta(hours=1)
            rows = [
                telemetry_row(
                    tenant_id=tenant.id,
                    sensor_id=sensor.id,
                    machine_id=machine.id,
                    source_timestamp=start + timedelta(seconds=5 * i),
                    value=50.0,
                    measurement_type=SensorType.MACHINE_POWER,
                )
                for i in range(40)
            ]
            # One more real reading, the "latest" the API reads.
            rows.append(
                telemetry_row(
                    tenant_id=tenant.id,
                    sensor_id=sensor.id,
                    machine_id=machine.id,
                    source_timestamp=now,
                    value=50.0,
                    measurement_type=SensorType.MACHINE_POWER,
                )
            )
            await insert_rows(session, rows)

            engine = BaselineEngine(session, load_baseline_policy())
            for _ in range(3):
                await engine.refresh_sensor(tenant.id, sensor, now, window_override=(start, now))

            await session.commit()
            yield SeededEnergyAssessment(tenant=tenant, machine=machine, sensor=sensor)
    finally:
        await database.dispose()


def test_latest_energy_assessment_requires_tenant_header(
    client: TestClient, seeded_energy_machine: SeededEnergyAssessment
) -> None:
    response = client.get(f"/api/v1/energy/machines/{seeded_energy_machine.machine.id}/latest")
    assert response.status_code == 400


def test_latest_energy_assessment_computes_and_returns_evidence(
    client: TestClient, seeded_energy_machine: SeededEnergyAssessment
) -> None:
    response = client.get(
        f"/api/v1/energy/machines/{seeded_energy_machine.machine.id}/latest",
        headers={TENANT_HEADER: str(seeded_energy_machine.tenant.id)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "WITHIN_EXPECTED_RANGE"
    assert body["actual_power_kw"] == 50.0
    assert body["expected_power_kw"] is not None
    assert body["power_sensor_id"] == str(seeded_energy_machine.sensor.id)
    assert body["tenant_id"] == str(seeded_energy_machine.tenant.id)


def test_latest_energy_assessment_404_for_unknown_machine(
    client: TestClient, seeded_energy_machine: SeededEnergyAssessment
) -> None:
    response = client.get(
        f"/api/v1/energy/machines/{uuid.uuid4()}/latest",
        headers={TENANT_HEADER: str(seeded_energy_machine.tenant.id)},
    )
    assert response.status_code == 404


def test_fleet_latest_includes_seeded_machine(
    client: TestClient, seeded_energy_machine: SeededEnergyAssessment
) -> None:
    # Compute-and-persist first (fleet-latest is read-only, never triggers assessment).
    client.get(
        f"/api/v1/energy/machines/{seeded_energy_machine.machine.id}/latest",
        headers={TENANT_HEADER: str(seeded_energy_machine.tenant.id)},
    )
    response = client.get(
        "/api/v1/energy/fleet-latest",
        headers={TENANT_HEADER: str(seeded_energy_machine.tenant.id)},
    )
    assert response.status_code == 200
    machine_ids = {row["machine_id"] for row in response.json()}
    assert str(seeded_energy_machine.machine.id) in machine_ids


def test_history_returns_persisted_assessments(
    client: TestClient, seeded_energy_machine: SeededEnergyAssessment
) -> None:
    client.get(
        f"/api/v1/energy/machines/{seeded_energy_machine.machine.id}/latest",
        headers={TENANT_HEADER: str(seeded_energy_machine.tenant.id)},
    )
    response = client.get(
        f"/api/v1/energy/machines/{seeded_energy_machine.machine.id}/history",
        headers={TENANT_HEADER: str(seeded_energy_machine.tenant.id)},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) >= 1
    assert body[0]["status"] == "WITHIN_EXPECTED_RANGE"
