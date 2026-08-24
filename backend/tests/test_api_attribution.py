"""API-level tests for `/api/v1/energy/*/attribution/*` — real HTTP requests via
`TestClient` against real Postgres, mirroring `tests/test_api_energy.py`'s committed
-fixture convention: seed real telemetry, let the real `BaselineEngine` build a real
baseline, then let the real service compute and persist the assessment/attribution
through the actual API route."""

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
class SeededAttributionMachine:
    tenant: Tenant
    machine: Machine
    sensor: Sensor


@pytest_asyncio.fixture
async def seeded_elevated_energy_machine() -> AsyncIterator[SeededAttributionMachine]:
    """Elevated power with no independent lubrication/mechanical evidence seeded —
    exercises the NO_EVIDENCE path (energy alone is never sufficient) end-to-end
    through the real API route."""
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
            rows.append(
                telemetry_row(
                    tenant_id=tenant.id,
                    sensor_id=sensor.id,
                    machine_id=machine.id,
                    source_timestamp=now,
                    value=90.0,
                    measurement_type=SensorType.MACHINE_POWER,
                )
            )
            await insert_rows(session, rows)

            engine = BaselineEngine(session, load_baseline_policy())
            for _ in range(3):
                await engine.refresh_sensor(tenant.id, sensor, now, window_override=(start, now))

            await session.commit()
            yield SeededAttributionMachine(tenant=tenant, machine=machine, sensor=sensor)
    finally:
        await database.dispose()


def test_attribution_requires_tenant_header(
    client: TestClient, seeded_elevated_energy_machine: SeededAttributionMachine
) -> None:
    response = client.get(
        f"/api/v1/energy/machines/{seeded_elevated_energy_machine.machine.id}/attribution/latest"
    )
    assert response.status_code == 400


def test_attribution_404_when_no_energy_assessment_exists(
    client: TestClient, seeded_elevated_energy_machine: SeededAttributionMachine
) -> None:
    # Attribution is requested before any /energy/.../latest call has ever persisted
    # an EnergyAssessment for this machine.
    response = client.get(
        f"/api/v1/energy/machines/{seeded_elevated_energy_machine.machine.id}/attribution/latest",
        headers={TENANT_HEADER: str(seeded_elevated_energy_machine.tenant.id)},
    )
    assert response.status_code == 404


def test_attribution_404_for_unknown_machine(
    client: TestClient, seeded_elevated_energy_machine: SeededAttributionMachine
) -> None:
    response = client.get(
        f"/api/v1/energy/machines/{uuid.uuid4()}/attribution/latest",
        headers={TENANT_HEADER: str(seeded_elevated_energy_machine.tenant.id)},
    )
    assert response.status_code == 404


def test_elevated_energy_with_no_independent_evidence_is_no_evidence(
    client: TestClient, seeded_elevated_energy_machine: SeededAttributionMachine
) -> None:
    machine_id = seeded_elevated_energy_machine.machine.id
    tenant_id = seeded_elevated_energy_machine.tenant.id
    energy_response = client.get(
        f"/api/v1/energy/machines/{machine_id}/latest",
        headers={TENANT_HEADER: str(tenant_id)},
    )
    assert energy_response.status_code == 200
    assert energy_response.json()["status"] == "ELEVATED_ENERGY_DEMAND"

    response = client.get(
        f"/api/v1/energy/machines/{machine_id}/attribution/latest",
        headers={TENANT_HEADER: str(tenant_id)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["attribution_level"] == "NO_EVIDENCE"
    assert body["machine_id"] == str(machine_id)
    assert body["tenant_id"] == str(tenant_id)
    assert body["energy_residual_kw"] is not None
    assert body["energy_residual_kw"] > 0
    # The energy observation itself is always surfaced as context (necessary but never
    # sufficient) — NO_EVIDENCE means no *independent* lubrication/mechanical evidence
    # family was found, not that supporting_evidence is empty.
    assert any("power" in item.lower() for item in body["supporting_evidence"])
    assert not any(
        keyword in item.lower()
        for item in body["supporting_evidence"]
        for keyword in ("bearing", "vibration", "pressure", "flow", "reservoir")
    )


def test_fleet_latest_attribution_includes_seeded_machine(
    client: TestClient, seeded_elevated_energy_machine: SeededAttributionMachine
) -> None:
    machine_id = seeded_elevated_energy_machine.machine.id
    tenant_id = seeded_elevated_energy_machine.tenant.id
    client.get(
        f"/api/v1/energy/machines/{machine_id}/latest", headers={TENANT_HEADER: str(tenant_id)}
    )
    client.get(
        f"/api/v1/energy/machines/{machine_id}/attribution/latest",
        headers={TENANT_HEADER: str(tenant_id)},
    )

    response = client.get(
        "/api/v1/energy/attribution/fleet-latest", headers={TENANT_HEADER: str(tenant_id)}
    )
    assert response.status_code == 200
    machine_ids = {row["machine_id"] for row in response.json()}
    assert str(machine_id) in machine_ids


def test_attribution_history_returns_persisted_assessments(
    client: TestClient, seeded_elevated_energy_machine: SeededAttributionMachine
) -> None:
    machine_id = seeded_elevated_energy_machine.machine.id
    tenant_id = seeded_elevated_energy_machine.tenant.id
    client.get(
        f"/api/v1/energy/machines/{machine_id}/latest", headers={TENANT_HEADER: str(tenant_id)}
    )
    client.get(
        f"/api/v1/energy/machines/{machine_id}/attribution/latest",
        headers={TENANT_HEADER: str(tenant_id)},
    )

    response = client.get(
        f"/api/v1/energy/machines/{machine_id}/attribution/history",
        headers={TENANT_HEADER: str(tenant_id)},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) >= 1
    assert body[0]["attribution_level"] == "NO_EVIDENCE"


def test_tenant_isolation_on_attribution(
    client: TestClient, seeded_elevated_energy_machine: SeededAttributionMachine
) -> None:
    machine_id = seeded_elevated_energy_machine.machine.id
    other_tenant_id = uuid.uuid4()

    response = client.get(
        f"/api/v1/energy/machines/{machine_id}/attribution/latest",
        headers={TENANT_HEADER: str(other_tenant_id)},
    )
    assert response.status_code in (400, 404)
