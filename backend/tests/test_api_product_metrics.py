"""Phase 22 product-metrics API: contract shape and RBAC via the real HTTP surface."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.domain.models import Tenant


def test_product_metrics_returns_north_star_and_supporting(
    client: TestClient, api_tenant: Tenant
) -> None:
    response = client.get(
        "/api/v1/product-metrics", headers={"X-Tenant-ID": str(api_tenant.id)}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["north_star"]["metric_id"] == "north_star.meaningful_issues_detected_with_lead_time"
    assert body["north_star"]["provenance"] == "DEMO_ESTIMATE"
    assert len(body["supporting"]) > 5
    for metric in body["supporting"]:
        assert metric["provenance"] in (
            "MEASURED_PLATFORM_METRIC",
            "DEMO_ESTIMATE",
            "CONFIGURED_TARGET",
        )


def test_north_star_endpoint(client: TestClient, api_tenant: Tenant) -> None:
    response = client.get(
        "/api/v1/product-metrics/north-star", headers={"X-Tenant-ID": str(api_tenant.id)}
    )
    assert response.status_code == 200
    assert response.json()["unit"] == "ratio"
