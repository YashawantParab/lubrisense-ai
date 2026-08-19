"""Phase 12 state-estimation API: tenant scoping, contract shape, and machine-not-found
handling. Unlike Phase 11's ML API, `/latest` has no "no VALIDATED model registered" 503
case — the filter always exists (it's configuration-driven, not a trained-model registry
lookup) — so a fresh, sensor-less machine's `/latest` call is expected to succeed at 200
with `prediction_only=True` for both state types, not 503.
"""

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
    response = client.get(
        f"/api/v1/state-estimation/machines/{uuid.uuid4()}/latest", headers=headers
    )
    assert response.status_code == 404


def test_history_machine_not_found(client: TestClient, api_tenant: Tenant) -> None:
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    response = client.get(
        f"/api/v1/state-estimation/machines/{uuid.uuid4()}/history", headers=headers
    )
    assert response.status_code == 404


def test_cross_tenant_machine_is_not_found(client: TestClient) -> None:
    tenant_a = asyncio.run(_committed_tenant())
    tenant_b = asyncio.run(_committed_tenant())
    machine_id = asyncio.run(_committed_machine(tenant_a))

    headers_b = {"X-Tenant-ID": str(tenant_b.id)}
    response = client.get(
        f"/api/v1/state-estimation/machines/{machine_id}/latest", headers=headers_b
    )
    assert response.status_code == 404


def test_history_returns_empty_list_for_fresh_machine(
    client: TestClient, api_tenant: Tenant
) -> None:
    machine_id = asyncio.run(_committed_machine(api_tenant))
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    response = client.get(
        f"/api/v1/state-estimation/machines/{machine_id}/history", headers=headers
    )
    assert response.status_code == 200
    assert response.json() == []


def test_unknown_state_type_history_filter_rejected(
    client: TestClient, api_tenant: Tenant
) -> None:
    machine_id = asyncio.run(_committed_machine(api_tenant))
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    response = client.get(
        f"/api/v1/state-estimation/machines/{machine_id}/history",
        params={"state_type": "NOT_A_REAL_STATE"},
        headers=headers,
    )
    assert response.status_code == 422


def test_latest_on_fresh_machine_computes_both_states_as_prediction_only(
    client: TestClient, api_tenant: Tenant
) -> None:
    """A freshly created machine has no sensors/telemetry, so both configured state types
    should compute successfully (200) with zero observation channels available — never a
    crash, never a fabricated observation."""
    machine_id = asyncio.run(_committed_machine(api_tenant))
    headers = {"X-Tenant-ID": str(api_tenant.id)}

    response = client.get(
        f"/api/v1/state-estimation/machines/{machine_id}/latest", headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"LUBRICATION_DELIVERY_STATE", "BEARING_CONDITION_STATE"}
    for state_type, estimate in body.items():
        assert estimate["state_type"] == state_type
        assert estimate["prediction_only"] is True
        assert estimate["observations_used"] == []
        assert 0.0 <= estimate["state_value"] <= 1.0
        assert estimate["trend"] in ("IMPROVING", "STABLE", "DETERIORATING", "UNKNOWN")
        assert estimate["uncertainty"] in ("LOW", "MODERATE", "HIGH")


def test_latest_persists_and_history_reflects_it(client: TestClient, api_tenant: Tenant) -> None:
    machine_id = asyncio.run(_committed_machine(api_tenant))
    headers = {"X-Tenant-ID": str(api_tenant.id)}

    latest_response = client.get(
        f"/api/v1/state-estimation/machines/{machine_id}/latest", headers=headers
    )
    assert latest_response.status_code == 200

    history_response = client.get(
        f"/api/v1/state-estimation/machines/{machine_id}/history", headers=headers
    )
    assert history_response.status_code == 200
    history = history_response.json()
    assert len(history) == 2
    assert {row["state_type"] for row in history} == {
        "LUBRICATION_DELIVERY_STATE",
        "BEARING_CONDITION_STATE",
    }


def test_metrics_endpoint_returns_prometheus_text(client: TestClient) -> None:
    response = client.get("/api/v1/state-estimation/metrics")
    assert response.status_code == 200
    assert "state_estimates_computed" in response.text or response.text.strip() == ""
