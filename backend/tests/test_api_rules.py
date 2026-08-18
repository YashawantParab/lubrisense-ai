"""API-level tests for `/api/v1/rules/*` — real HTTP requests via `TestClient` against
real Postgres, seeded by running the real `RuleEngine` against committed telemetry
(mirrors `tests/test_api_baselines.py`'s committed-fixture convention)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from fastapi.testclient import TestClient

from app.baselines.config.policy import load_baseline_policy
from app.core.config import get_settings
from app.domain.enums import BaselineStrategyType, Eligibility, SensorType
from app.domain.models import Machine, Tenant
from app.infrastructure.database import Database
from app.rules_engine.config.policy import load_rules_policy
from app.rules_engine.repositories.rule_finding_repository import RuleFindingRepository
from app.rules_engine.services.rule_engine import RuleEngine
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
from tests.rules_engine.helpers import (
    create_active_baseline,
    insert_rows,
    robust_stats,
    set_eligibility,
    telemetry_row,
)

TENANT_HEADER = "X-Tenant-ID"


@dataclass(frozen=True)
class SeededFinding:
    tenant: Tenant
    machine: Machine
    finding_id: uuid.UUID


@pytest_asyncio.fixture
async def seeded_finding() -> AsyncIterator[SeededFinding]:
    database = Database(get_settings())
    try:
        async with database.session() as session:
            tenant = await make_tenant(session)
            customer = await make_customer(session, tenant)
            site = await make_site(session, tenant, customer)
            plant = await make_plant(session, tenant, site)
            line = await make_production_line(session, tenant, plant)
            machine = await make_machine(session, tenant, line)
            _bearing = await make_bearing(session, tenant, machine)
            system = await make_lubrication_system(session, tenant, machine)
            circuit = await make_circuit(session, tenant, system)
            sensor = await make_sensor(
                session, tenant, sensor_type=SensorType.PRESSURE, circuit_id=circuit.id
            )

            now = datetime.now(UTC)
            start = now - timedelta(hours=1)
            await create_active_baseline(
                session,
                tenant_id=tenant.id,
                sensor_id=sensor.id,
                machine_id=machine.id,
                measurement_type="PRESSURE",
                strategy=BaselineStrategyType.ROLLING_ASSET_BASELINE,
                context_key="",
                statistics=robust_stats(median=9.0, mad=0.5),
            )
            rows = [
                telemetry_row(
                    tenant_id=tenant.id,
                    sensor_id=sensor.id,
                    machine_id=machine.id,
                    circuit_id=circuit.id,
                    source_timestamp=start + timedelta(seconds=5 * i),
                    value=25.0,
                    measurement_type=SensorType.PRESSURE,
                )
                for i in range(30)
            ]
            await insert_rows(session, rows)
            await set_eligibility(session, tenant.id, sensor.id, machine.id, Eligibility.ELIGIBLE)

            engine = RuleEngine(session, load_baseline_policy(), load_rules_policy())
            result = None
            for _ in range(3):
                result = await engine.evaluate_machine(
                    tenant.id, machine.id, now, window_override=(start, now)
                )
            assert result is not None and result.findings_created + result.findings_updated > 0

            await session.commit()

            findings = await RuleFindingRepository(session).list_current_for_machine(
                tenant.id, machine.id
            )
            pressure_finding = next(
                f for f in findings if f.finding_type.value == "PRESSURE_ABOVE_CONTEXTUAL_BASELINE"
            )
            yield SeededFinding(tenant=tenant, machine=machine, finding_id=pressure_finding.id)
    finally:
        await database.dispose()


def test_list_findings_requires_tenant_header(
    client: TestClient, seeded_finding: SeededFinding
) -> None:
    response = client.get("/api/v1/rules/findings")
    assert response.status_code == 400


def test_list_findings_returns_active_finding(
    client: TestClient, seeded_finding: SeededFinding
) -> None:
    response = client.get(
        "/api/v1/rules/findings",
        headers={TENANT_HEADER: str(seeded_finding.tenant.id)},
    )
    assert response.status_code == 200
    body = response.json()
    assert any(f["id"] == str(seeded_finding.finding_id) for f in body)
    finding = next(f for f in body if f["id"] == str(seeded_finding.finding_id))
    assert finding["state"] == "ACTIVE"
    assert finding["finding_type"] == "PRESSURE_ABOVE_CONTEXTUAL_BASELINE"
    assert "observed" in str(finding["evidence"])
    assert finding["limitations"]


def test_get_finding_by_id(client: TestClient, seeded_finding: SeededFinding) -> None:
    response = client.get(
        f"/api/v1/rules/findings/{seeded_finding.finding_id}",
        headers={TENANT_HEADER: str(seeded_finding.tenant.id)},
    )
    assert response.status_code == 200
    assert response.json()["id"] == str(seeded_finding.finding_id)


def test_get_finding_404_for_unknown_id(client: TestClient, seeded_finding: SeededFinding) -> None:
    response = client.get(
        f"/api/v1/rules/findings/{uuid.uuid4()}",
        headers={TENANT_HEADER: str(seeded_finding.tenant.id)},
    )
    assert response.status_code == 404


def test_machine_findings_returns_current_findings(
    client: TestClient, seeded_finding: SeededFinding
) -> None:
    response = client.get(
        f"/api/v1/rules/machines/{seeded_finding.machine.id}",
        headers={TENANT_HEADER: str(seeded_finding.tenant.id)},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["findings"]) >= 1


def test_machine_findings_404_for_unknown_machine(
    client: TestClient, seeded_finding: SeededFinding
) -> None:
    response = client.get(
        f"/api/v1/rules/machines/{uuid.uuid4()}",
        headers={TENANT_HEADER: str(seeded_finding.tenant.id)},
    )
    assert response.status_code == 404


def test_summary_counts_active_findings(client: TestClient, seeded_finding: SeededFinding) -> None:
    response = client.get(
        "/api/v1/rules/summary", headers={TENANT_HEADER: str(seeded_finding.tenant.id)}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_active_findings"] >= 1
    assert body["findings_by_state"]["ACTIVE"] >= 1


def test_filter_findings_by_severity(client: TestClient, seeded_finding: SeededFinding) -> None:
    response = client.get(
        "/api/v1/rules/findings",
        params={"severity": "WARNING"},
        headers={TENANT_HEADER: str(seeded_finding.tenant.id)},
    )
    assert response.status_code == 200
    body = response.json()
    assert all(f["severity"] == "WARNING" for f in body)
