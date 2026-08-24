"""API-level tests for `/api/v1/performance/*` — real HTTP requests via `TestClient`
against real Postgres (Portfolio Intelligence Pass 1, ADR-177)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest_asyncio
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.domain.enums import (
    ConditionConfidence,
    ConditionLifecycle,
    ConditionSeverity,
    ConditionType,
)
from app.domain.models import ConditionAssessment, Machine, Site, Tenant
from app.infrastructure.database import Database
from tests.factories import (
    make_customer,
    make_machine,
    make_plant,
    make_production_line,
    make_site,
    make_tenant,
)

TENANT_HEADER = "X-Tenant-ID"


@pytest_asyncio.fixture
async def empty_tenant() -> AsyncIterator[Tenant]:
    database = Database(get_settings())
    try:
        async with database.session() as session:
            tenant = await make_tenant(session)
            await session.commit()
            yield tenant
    finally:
        await database.dispose()


@dataclass(frozen=True)
class SeededPortfolio:
    tenant: Tenant
    site: Site
    machine: Machine


@pytest_asyncio.fixture
async def seeded_portfolio() -> AsyncIterator[SeededPortfolio]:
    database = Database(get_settings())
    try:
        async with database.session() as session:
            tenant = await make_tenant(session)
            customer = await make_customer(session, tenant)
            site = await make_site(session, tenant, customer)
            plant = await make_plant(session, tenant, site)
            line = await make_production_line(session, tenant, plant)
            machine = await make_machine(session, tenant, line)
            machine.metadata_ = {"area": "Crushing"}
            await session.flush()

            condition = ConditionAssessment(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                machine_id=machine.id,
                component_id=None,
                condition_type=ConditionType.DEVELOPING_RESTRICTION_PATTERN,
                lifecycle_state=ConditionLifecycle.DETECTED,
                severity=ConditionSeverity.CRITICAL,
                confidence=ConditionConfidence.HIGH,
                as_of_timestamp=datetime.now(UTC),
                first_detected_at=datetime.now(UTC),
                evidence_summary={},
                rule_finding_ids=[],
                ml_result_ids=[],
                state_estimate_ids=[],
                quality_context={},
                baseline_versions={},
                instrumentation_coverage={},
                limitations=[],
                recommended_next_evidence=None,
                policy_version="1",
                engine_version="1",
            )
            session.add(condition)
            await session.commit()

            yield SeededPortfolio(tenant=tenant, site=site, machine=machine)
    finally:
        await database.dispose()


def test_organization_performance_requires_tenant_header(client: TestClient) -> None:
    response = client.get("/api/v1/performance/organization")
    assert response.status_code == 400


def test_organization_performance(client: TestClient, seeded_portfolio: SeededPortfolio) -> None:
    response = client.get(
        "/api/v1/performance/organization",
        headers={TENANT_HEADER: str(seeded_portfolio.tenant.id)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["portfolio"]["monitored_assets"] == 1
    assert body["portfolio"]["sites"] == 1
    assert body["reliability"]["critical_attention_assets"] == 1
    assert body["provenance"] == "MEASURED_PLATFORM_METRIC"


def test_site_performance_list(client: TestClient, seeded_portfolio: SeededPortfolio) -> None:
    response = client.get(
        "/api/v1/performance/sites",
        headers={TENANT_HEADER: str(seeded_portfolio.tenant.id)},
    )
    assert response.status_code == 200
    codes = {row["site_code"] for row in response.json()}
    assert seeded_portfolio.site.code in codes


def test_site_performance_by_id(client: TestClient, seeded_portfolio: SeededPortfolio) -> None:
    response = client.get(
        f"/api/v1/performance/sites/{seeded_portfolio.site.id}",
        headers={TENANT_HEADER: str(seeded_portfolio.tenant.id)},
    )
    assert response.status_code == 200
    assert response.json()["asset_count"] == 1


def test_site_performance_404_for_unknown_site(
    client: TestClient, seeded_portfolio: SeededPortfolio
) -> None:
    response = client.get(
        f"/api/v1/performance/sites/{uuid.uuid4()}",
        headers={TENANT_HEADER: str(seeded_portfolio.tenant.id)},
    )
    assert response.status_code == 404


def test_area_performance_list(client: TestClient, seeded_portfolio: SeededPortfolio) -> None:
    response = client.get(
        "/api/v1/performance/areas",
        headers={TENANT_HEADER: str(seeded_portfolio.tenant.id)},
    )
    assert response.status_code == 200
    areas = {row["area"] for row in response.json()}
    assert "Crushing" in areas


def test_area_performance_by_key(client: TestClient, seeded_portfolio: SeededPortfolio) -> None:
    response = client.get(
        "/api/v1/performance/areas/Crushing",
        headers={TENANT_HEADER: str(seeded_portfolio.tenant.id)},
    )
    assert response.status_code == 200
    assert response.json()["asset_count"] == 1


def test_area_performance_404_for_unknown_area(
    client: TestClient, seeded_portfolio: SeededPortfolio
) -> None:
    response = client.get(
        "/api/v1/performance/areas/Nonexistent",
        headers={TENANT_HEADER: str(seeded_portfolio.tenant.id)},
    )
    assert response.status_code == 404


def test_attention_queue(client: TestClient, seeded_portfolio: SeededPortfolio) -> None:
    response = client.get(
        "/api/v1/performance/attention",
        headers={TENANT_HEADER: str(seeded_portfolio.tenant.id)},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["priority"] == "CRITICAL_ATTENTION"
    assert body[0]["reasons"]


def test_recent_outcomes(client: TestClient, seeded_portfolio: SeededPortfolio) -> None:
    response = client.get(
        "/api/v1/performance/outcomes",
        headers={TENANT_HEADER: str(seeded_portfolio.tenant.id)},
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_tenant_isolation(client: TestClient, seeded_portfolio: SeededPortfolio) -> None:
    response = client.get(
        "/api/v1/performance/organization", headers={TENANT_HEADER: str(uuid.uuid4())}
    )
    assert response.status_code == 404


def test_empty_tenant_organization_performance(client: TestClient, empty_tenant: Tenant) -> None:
    response = client.get(
        "/api/v1/performance/organization", headers={TENANT_HEADER: str(empty_tenant.id)}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["portfolio"]["monitored_assets"] == 0
    assert body["top_attention_assets"] == []
