"""Phase 14 decision-intelligence API: tenant scoping, contract shape, machine-not-found
handling. A fresh machine's `/latest` succeeds at 200 with a monitoring/verification
recommendation, never a fabricated maintenance action."""

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


def test_latest_machine_not_found(client: TestClient, api_tenant: Tenant) -> None:
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    response = client.get(f"/api/v1/decisions/machines/{uuid.uuid4()}/latest", headers=headers)
    assert response.status_code == 404


def test_history_machine_not_found(client: TestClient, api_tenant: Tenant) -> None:
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    response = client.get(f"/api/v1/decisions/machines/{uuid.uuid4()}/history", headers=headers)
    assert response.status_code == 404


def test_cross_tenant_machine_is_not_found(client: TestClient) -> None:
    tenant_a = asyncio.run(_committed_tenant())
    tenant_b = asyncio.run(_committed_tenant())
    machine_id = asyncio.run(_committed_machine(tenant_a))

    headers_b = {"X-Tenant-ID": str(tenant_b.id)}
    response = client.get(f"/api/v1/decisions/machines/{machine_id}/latest", headers=headers_b)
    assert response.status_code == 404


def test_history_returns_empty_list_for_fresh_machine(
    client: TestClient, api_tenant: Tenant
) -> None:
    machine_id = asyncio.run(_committed_machine(api_tenant))
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    response = client.get(f"/api/v1/decisions/machines/{machine_id}/history", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


def test_latest_on_fresh_machine_never_fabricates_a_maintenance_action(
    client: TestClient, api_tenant: Tenant
) -> None:
    machine_id = asyncio.run(_committed_machine(api_tenant))
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    response = client.get(f"/api/v1/decisions/machines/{machine_id}/latest", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["recommended_action"] == "REQUEST_ADDITIONAL_MEASUREMENT"
    assert body["human_review_required"] is False
    assert body["lifecycle_state"] == "ACTIVE"


def test_second_call_supersedes_first_via_api(client: TestClient, api_tenant: Tenant) -> None:
    machine_id = asyncio.run(_committed_machine(api_tenant))
    headers = {"X-Tenant-ID": str(api_tenant.id)}

    first = client.get(f"/api/v1/decisions/machines/{machine_id}/latest", headers=headers)
    second = client.get(f"/api/v1/decisions/machines/{machine_id}/latest", headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200

    history = client.get(f"/api/v1/decisions/machines/{machine_id}/history", headers=headers).json()
    assert len(history) == 2
    lifecycle_states = {row["id"]: row["lifecycle_state"] for row in history}
    assert lifecycle_states[first.json()["id"]] == "SUPERSEDED"
    assert lifecycle_states[second.json()["id"]] == "ACTIVE"
