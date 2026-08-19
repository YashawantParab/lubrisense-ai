"""Phase 11 ML API: tenant scoping, contract shape, and machine/model not-found handling.

Deliberately does not assert a hard-coded "OK" inference result for a live now() feature
vector: whether `GET /machines/{id}/latest` returns 200 (with status OK/UNKNOWN/
INSUFFICIENT_FEATURES) or 503 depends on whether `ml-service` has a VALIDATED model
registered on disk at test time (`ml-service/artifacts/models/`), which is populated by
`python -m ml_service.training.train_anomaly`/`train_classifier`, not by this test suite.
The end-to-end "a real registered model scores a real feature vector" proof lives in
`scripts/verify_ml_pipeline.py` (run against the live stack with training already done),
per LOOP.md's "do not substitute a hand-constructed feature vector as the only acceptance
test."
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


def test_unknown_model_id_rejected(client: TestClient, api_tenant: Tenant) -> None:
    machine_id = asyncio.run(_committed_machine(api_tenant))
    headers = {"X-Tenant-ID": str(api_tenant.id)}

    response = client.get(
        f"/api/v1/ml/machines/{machine_id}/latest",
        params={"model_id": "NOT_A_REAL_MODEL"},
        headers=headers,
    )
    assert response.status_code == 422


def test_latest_machine_not_found(client: TestClient, api_tenant: Tenant) -> None:
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    response = client.get(
        f"/api/v1/ml/machines/{uuid.uuid4()}/latest",
        params={"model_id": "LUBRICATION_ANOMALY_V1"},
        headers=headers,
    )
    assert response.status_code == 404


def test_history_machine_not_found(client: TestClient, api_tenant: Tenant) -> None:
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    response = client.get(f"/api/v1/ml/machines/{uuid.uuid4()}/history", headers=headers)
    assert response.status_code == 404


def test_cross_tenant_machine_is_not_found(client: TestClient) -> None:
    tenant_a = asyncio.run(_committed_tenant())
    tenant_b = asyncio.run(_committed_tenant())
    machine_id = asyncio.run(_committed_machine(tenant_a))

    headers_b = {"X-Tenant-ID": str(tenant_b.id)}
    response = client.get(
        f"/api/v1/ml/machines/{machine_id}/latest",
        params={"model_id": "LUBRICATION_ANOMALY_V1"},
        headers=headers_b,
    )
    assert response.status_code == 404


def test_history_returns_empty_list_for_fresh_machine(
    client: TestClient, api_tenant: Tenant
) -> None:
    machine_id = asyncio.run(_committed_machine(api_tenant))
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    response = client.get(f"/api/v1/ml/machines/{machine_id}/history", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


def test_latest_on_fresh_machine_is_either_unavailable_or_insufficient_features(
    client: TestClient, api_tenant: Tenant
) -> None:
    """A freshly created machine has no sensors/telemetry, so if a model IS registered the
    computed feature vector is entirely missing -> INSUFFICIENT_FEATURES; if no VALIDATED
    model is registered yet, the service correctly reports 503, not a crash."""
    machine_id = asyncio.run(_committed_machine(api_tenant))
    headers = {"X-Tenant-ID": str(api_tenant.id)}

    response = client.get(
        f"/api/v1/ml/machines/{machine_id}/latest",
        params={"model_id": "LUBRICATION_ANOMALY_V1"},
        headers=headers,
    )
    assert response.status_code in (200, 503)
    if response.status_code == 200:
        assert response.json()["status"] == "INSUFFICIENT_FEATURES"


def test_get_unknown_model_detail_404(client: TestClient, api_tenant: Tenant) -> None:
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    response = client.get("/api/v1/ml/models/DEFINITELY_NOT_REGISTERED", headers=headers)
    assert response.status_code == 404


def test_list_models_is_always_200(client: TestClient, api_tenant: Tenant) -> None:
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    response = client.get("/api/v1/ml/models", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)
