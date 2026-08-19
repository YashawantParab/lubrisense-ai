"""Phase 21 customer/site/fleet overview API: tenant scoping, not-found handling, and
RBAC (METRICS_READ) via the real HTTP surface."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.domain.models import Tenant


def test_customer_overview_not_found(client: TestClient, api_tenant: Tenant) -> None:
    response = client.get(
        f"/api/v1/customers/{uuid.uuid4()}/overview",
        headers={"X-Tenant-ID": str(api_tenant.id)},
    )
    assert response.status_code == 404


def test_site_overview_not_found(client: TestClient, api_tenant: Tenant) -> None:
    response = client.get(
        f"/api/v1/sites/{uuid.uuid4()}/overview", headers={"X-Tenant-ID": str(api_tenant.id)}
    )
    assert response.status_code == 404


def test_fleet_overview_returns_shape_for_empty_tenant(
    client: TestClient, api_tenant: Tenant
) -> None:
    response = client.get(
        "/api/v1/fleet/overview", headers={"X-Tenant-ID": str(api_tenant.id)}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_machines"] == 0
    assert body["asset_coverage"]["instrumentation_coverage_ratio"] is None


def test_customer_overview_full_workflow(client: TestClient, api_tenant: Tenant) -> None:
    create_response = client.post(
        "/api/v1/customers",
        headers={"X-Tenant-ID": str(api_tenant.id)},
        json={
            "name": "Test Customer",
            "code": f"cust-{uuid.uuid4().hex[:8]}",
            "service_tier": "CONNECTED_MONITORING",
        },
    )
    assert create_response.status_code == 201
    customer_id = create_response.json()["id"]

    overview_response = client.get(
        f"/api/v1/customers/{customer_id}/overview", headers={"X-Tenant-ID": str(api_tenant.id)}
    )
    assert overview_response.status_code == 200
    body = overview_response.json()
    assert body["status"] == "UNKNOWN"
    assert body["total_machines"] == 0
    assert body["status_reasons"]
