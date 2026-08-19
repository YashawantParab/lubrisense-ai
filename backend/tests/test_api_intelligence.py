"""Combined `/intelligence/machines/{id}` view: tenant scoping, machine-not-found handling,
and internal consistency between the three bundled sub-objects (Phase 13-15 brief
"Integration" — condition/prognostics/decision persistence stays separate; this only
bundles one read of each)."""

from __future__ import annotations

import asyncio
import uuid

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.domain.models import Tenant
from app.infrastructure.database import Database
from tests.factories import (
    make_customer,
    make_machine,
    make_plant,
    make_production_line,
    make_site,
    make_tenant,
)


async def _committed_machine(tenant: Tenant) -> uuid.UUID:
    database = Database(get_settings())
    try:
        async with database.session() as session:
            customer = await make_customer(session, tenant)
            site = await make_site(session, tenant, customer)
            plant = await make_plant(session, tenant, site)
            line = await make_production_line(session, tenant, plant)
            machine = await make_machine(session, tenant, line)
            await session.commit()
            return machine.id
    finally:
        await database.dispose()


async def _committed_tenant() -> Tenant:
    database = Database(get_settings())
    try:
        async with database.session() as session:
            tenant = await make_tenant(session)
            await session.commit()
            return tenant
    finally:
        await database.dispose()


def test_intelligence_view_machine_not_found(client: TestClient, api_tenant: Tenant) -> None:
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    response = client.get(f"/api/v1/intelligence/machines/{uuid.uuid4()}", headers=headers)
    assert response.status_code == 404


def test_intelligence_view_cross_tenant_machine_is_not_found(client: TestClient) -> None:
    tenant_a = asyncio.run(_committed_tenant())
    tenant_b = asyncio.run(_committed_tenant())
    machine_id = asyncio.run(_committed_machine(tenant_a))

    headers_b = {"X-Tenant-ID": str(tenant_b.id)}
    response = client.get(f"/api/v1/intelligence/machines/{machine_id}", headers=headers_b)
    assert response.status_code == 404


def test_intelligence_view_on_fresh_machine_is_internally_consistent(
    client: TestClient, api_tenant: Tenant
) -> None:
    machine_id = asyncio.run(_committed_machine(api_tenant))
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    response = client.get(f"/api/v1/intelligence/machines/{machine_id}", headers=headers)
    assert response.status_code == 200
    body = response.json()

    assert body["condition"]["condition_type"] == "INSUFFICIENT_EVIDENCE"
    assert body["prognostics"] == []
    assert body["decision"]["recommended_action"] == "REQUEST_ADDITIONAL_MEASUREMENT"
    assert body["decision"]["condition_assessment_id"] == body["condition"]["id"]


def test_intelligence_view_each_call_runs_a_fresh_consistent_chain(
    client: TestClient, api_tenant: Tenant
) -> None:
    machine_id = asyncio.run(_committed_machine(api_tenant))
    headers = {"X-Tenant-ID": str(api_tenant.id)}

    first = client.get(f"/api/v1/intelligence/machines/{machine_id}", headers=headers).json()
    second = client.get(f"/api/v1/intelligence/machines/{machine_id}", headers=headers).json()

    assert first["decision"]["id"] != second["decision"]["id"]
    assert second["decision"]["condition_assessment_id"] == second["condition"]["id"]
