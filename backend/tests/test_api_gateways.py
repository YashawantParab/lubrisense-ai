"""Gateway listing API: tenant scoping and optional site filter."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.domain.models import Tenant
from app.infrastructure.database import Database
from tests.factories import make_customer, make_gateway, make_site


async def _committed_gateway(tenant: Tenant) -> str:
    database = Database(get_settings())
    try:
        async with database.session() as session:
            customer = await make_customer(session, tenant)
            site = await make_site(session, tenant, customer)
            await make_gateway(session, tenant, site_id=site.id)
            await session.commit()
            return str(site.id)
    finally:
        await database.dispose()


def test_list_gateways_filters_by_site(client: TestClient, api_tenant: Tenant) -> None:
    site_id = asyncio.run(_committed_gateway(api_tenant))
    headers = {"X-Tenant-ID": str(api_tenant.id)}

    response = client.get("/api/v1/gateways", headers=headers, params={"site_id": site_id})
    assert response.status_code == 200
    assert len(response.json()) == 1

    other_response = client.get(
        "/api/v1/gateways",
        headers=headers,
        params={"site_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert other_response.status_code == 200
    assert other_response.json() == []
