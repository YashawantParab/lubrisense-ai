"""API-level tests for `/api/v1/baselines/*` — real HTTP requests via `TestClient` against
real Postgres, seeded by running the real `BaselineEngine` against committed telemetry
(mirrors `tests/test_api_telemetry.py`'s committed-fixture convention)."""

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
class SeededBaseline:
    tenant: Tenant
    machine: Machine
    sensor: Sensor


@pytest_asyncio.fixture
async def seeded_baseline() -> AsyncIterator[SeededBaseline]:
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
                session, tenant, sensor_type=SensorType.BEARING_TEMPERATURE, machine_id=machine.id
            )

            now = datetime.now(UTC)
            start = now - timedelta(hours=1)
            rows = [
                telemetry_row(
                    tenant_id=tenant.id,
                    sensor_id=sensor.id,
                    machine_id=machine.id,
                    source_timestamp=start + timedelta(seconds=5 * i),
                    value=45.0,
                    measurement_type=SensorType.BEARING_TEMPERATURE,
                )
                for i in range(40)
            ]
            await insert_rows(session, rows)

            engine = BaselineEngine(session, load_baseline_policy())
            await engine.refresh_sensor(tenant.id, sensor, now, window_override=(start, now))
            await engine.refresh_sensor(tenant.id, sensor, now, window_override=(start, now))

            await session.commit()
            yield SeededBaseline(tenant=tenant, machine=machine, sensor=sensor)
    finally:
        await database.dispose()


def test_sensor_baselines_requires_tenant_header(
    client: TestClient, seeded_baseline: SeededBaseline
) -> None:
    response = client.get(f"/api/v1/baselines/sensors/{seeded_baseline.sensor.id}")
    assert response.status_code == 400


def test_sensor_baselines_returns_active_profiles(
    client: TestClient, seeded_baseline: SeededBaseline
) -> None:
    response = client.get(
        f"/api/v1/baselines/sensors/{seeded_baseline.sensor.id}",
        headers={TENANT_HEADER: str(seeded_baseline.tenant.id)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["readiness"]["label"] == "READY"
    strategies = {p["strategy"] for p in body["profiles"]}
    assert "STATIC_ENGINEERING_REFERENCE" in strategies
    assert "ROLLING_ASSET_BASELINE" in strategies
    assert all(p["state"] == "ACTIVE" for p in body["profiles"])


def test_sensor_baselines_404_for_unknown_sensor(
    client: TestClient, seeded_baseline: SeededBaseline
) -> None:
    response = client.get(
        f"/api/v1/baselines/sensors/{uuid.uuid4()}",
        headers={TENANT_HEADER: str(seeded_baseline.tenant.id)},
    )
    assert response.status_code == 404


def test_current_baseline_resolves_and_computes_deviation(
    client: TestClient, seeded_baseline: SeededBaseline
) -> None:
    response = client.get(
        f"/api/v1/baselines/sensors/{seeded_baseline.sensor.id}/current",
        params={"value": 45.0},
        headers={TENANT_HEADER: str(seeded_baseline.tenant.id)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "SENSOR_LEVEL"
    assert body["profile"]["strategy"] == "ROLLING_ASSET_BASELINE"
    assert body["deviation"]["classification"] == "WITHIN_EXPECTED_RANGE"


def test_current_baseline_far_value_is_strong_deviation(
    client: TestClient, seeded_baseline: SeededBaseline
) -> None:
    response = client.get(
        f"/api/v1/baselines/sensors/{seeded_baseline.sensor.id}/current",
        params={"value": 145.0},
        headers={TENANT_HEADER: str(seeded_baseline.tenant.id)},
    )
    assert response.status_code == 200
    assert response.json()["deviation"]["classification"] == "STRONG_DEVIATION"


def test_machine_baselines_returns_sensor_profiles(
    client: TestClient, seeded_baseline: SeededBaseline
) -> None:
    response = client.get(
        f"/api/v1/baselines/machines/{seeded_baseline.machine.id}",
        headers={TENANT_HEADER: str(seeded_baseline.tenant.id)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["readiness"]["label"] == "READY"
    assert len(body["profiles"]) >= 2


def test_baseline_summary_counts_active_profiles(
    client: TestClient, seeded_baseline: SeededBaseline
) -> None:
    response = client.get(
        "/api/v1/baselines/summary", headers={TENANT_HEADER: str(seeded_baseline.tenant.id)}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["profiles_by_state"]["ACTIVE"] >= 2
    assert body["total_profiles"] >= 2
