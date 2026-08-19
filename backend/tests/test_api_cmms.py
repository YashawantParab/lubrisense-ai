"""Phase 20 CMMS read API: tenant scoping and not-found handling."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.domain.models import Tenant


def test_get_unknown_work_order_returns_404(client: TestClient, api_tenant: Tenant) -> None:
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    response = client.get("/api/v1/cmms/work-orders/DEMO-WO-NOTHING", headers=headers)
    assert response.status_code == 404


def test_cmms_metrics_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/cmms/metrics")
    assert response.status_code == 200
