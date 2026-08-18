"""API-level tests: real HTTP requests through the FastAPI TestClient against real
Postgres, exercising the tenant-context dependency, typed schemas, and the create/list/
get flow end to end."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.domain.models import Tenant

TENANT_HEADER = "X-Tenant-ID"


def test_customers_requires_tenant_header(client: TestClient) -> None:
    response = client.get("/api/v1/customers")

    assert response.status_code == 400
    assert response.json()["code"] == "TENANT_CONTEXT_REQUIRED"


def test_customers_rejects_unknown_tenant(client: TestClient) -> None:
    response = client.get("/api/v1/customers", headers={TENANT_HEADER: str(uuid.uuid4())})

    assert response.status_code == 404
    assert response.json()["code"] == "TENANT_NOT_FOUND"


def test_create_list_and_get_customer(client: TestClient, api_tenant: Tenant) -> None:
    headers = {TENANT_HEADER: str(api_tenant.id)}

    create_response = client.post(
        "/api/v1/customers",
        headers=headers,
        json={
            "name": "API Test Customer",
            "code": f"APITEST-{uuid.uuid4().hex[:8]}",
            "service_tier": "CONNECTED_MONITORING",
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["name"] == "API Test Customer"
    assert created["commercial_status"] == "PROSPECT"

    get_response = client.get(f"/api/v1/customers/{created['id']}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["id"] == created["id"]

    list_response = client.get("/api/v1/customers", headers=headers)
    assert list_response.status_code == 200
    body = list_response.json()
    assert body["meta"]["total"] >= 1
    assert any(item["id"] == created["id"] for item in body["items"])


def test_create_customer_duplicate_code_returns_409(client: TestClient, api_tenant: Tenant) -> None:
    headers = {TENANT_HEADER: str(api_tenant.id)}
    code = f"DUP-{uuid.uuid4().hex[:8]}"
    payload = {"name": "Dup Customer", "code": code, "service_tier": "CONNECTED_MONITORING"}

    first = client.post("/api/v1/customers", headers=headers, json=payload)
    assert first.status_code == 201

    second = client.post("/api/v1/customers", headers=headers, json=payload)
    assert second.status_code == 409
    assert second.json()["code"] == "CUSTOMER_ACCOUNT_CODE_TAKEN"


def test_get_unknown_customer_returns_404(client: TestClient, api_tenant: Tenant) -> None:
    headers = {TENANT_HEADER: str(api_tenant.id)}

    response = client.get(f"/api/v1/customers/{uuid.uuid4()}", headers=headers)

    assert response.status_code == 404
    assert response.json()["code"] == "CUSTOMER_ACCOUNT_NOT_FOUND"


def test_full_site_plant_line_machine_flow(client: TestClient, api_tenant: Tenant) -> None:
    headers = {TENANT_HEADER: str(api_tenant.id)}
    suffix = uuid.uuid4().hex[:8]

    customer = client.post(
        "/api/v1/customers",
        headers=headers,
        json={
            "name": "Flow Customer",
            "code": f"FLOW-{suffix}",
            "service_tier": "CONNECTED_MONITORING",
        },
    ).json()

    site = client.post(
        "/api/v1/sites",
        headers=headers,
        json={
            "customer_account_id": customer["id"],
            "name": "Flow Site",
            "code": f"FLOWSITE-{suffix}",
        },
    ).json()

    plant = client.post(
        "/api/v1/plants",
        headers=headers,
        json={"site_id": site["id"], "name": "Flow Plant", "code": f"FLOWPLANT-{suffix}"},
    ).json()

    line = client.post(
        "/api/v1/production-lines",
        headers=headers,
        json={"plant_id": plant["id"], "name": "Flow Line", "code": f"FLOWLINE-{suffix}"},
    ).json()

    machine = client.post(
        "/api/v1/machines",
        headers=headers,
        json={
            "production_line_id": line["id"],
            "name": "Flow Machine",
            "asset_code": f"FLOWASSET-{suffix}",
            "machine_type": "MOTOR",
        },
    ).json()

    hierarchy_response = client.get(f"/api/v1/machines/{machine['id']}/hierarchy", headers=headers)
    assert hierarchy_response.status_code == 200
    hierarchy = hierarchy_response.json()
    assert hierarchy["machine"]["id"] == machine["id"]
    assert hierarchy["bearings"] == []
    assert hierarchy["lubrication_systems"] == []
    assert hierarchy["sensors"] == []

    full_hierarchy = client.get("/api/v1/hierarchy", headers=headers).json()
    customer_ids = {c["id"] for c in full_hierarchy["customers"]}
    assert customer["id"] in customer_ids


def test_site_create_rejects_unknown_customer_via_api(
    client: TestClient, api_tenant: Tenant
) -> None:
    headers = {TENANT_HEADER: str(api_tenant.id)}

    response = client.post(
        "/api/v1/sites",
        headers=headers,
        json={
            "customer_account_id": str(uuid.uuid4()),
            "name": "Orphan Site",
            "code": f"ORPHAN-{uuid.uuid4().hex[:8]}",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "CUSTOMER_ACCOUNT_NOT_FOUND_FOR_SITE"
