"""Phase 26 observability: central HTTP metrics endpoint and correlation-ID
propagation through the response headers."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.domain.models import Tenant


def test_system_metrics_reflects_request_activity(client: TestClient, api_tenant: Tenant) -> None:
    client.get("/api/v1/incidents", headers={"X-Tenant-ID": str(api_tenant.id)})

    response = client.get("/api/v1/system/metrics")
    assert response.status_code == 200
    text = response.text
    assert "http_requests_total" in text
    assert "http_requests_total_2xx" in text


def test_health_and_readiness_endpoints() -> None:
    from app.main import create_app

    with TestClient(create_app()) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        ready = client.get("/ready")
        assert ready.status_code in (200, 503)
        assert "dependencies" in ready.json()


def test_correlation_id_present_and_echoed(client: TestClient, api_tenant: Tenant) -> None:
    response = client.get(
        "/api/v1/incidents",
        headers={"X-Tenant-ID": str(api_tenant.id), "X-Correlation-ID": "test-corr-abc123"},
    )
    assert response.headers["X-Correlation-ID"] == "test-corr-abc123"


def test_auth_failure_increments_metric(client: TestClient, api_tenant: Tenant) -> None:
    # /fleet/overview is one of the routes gated by require_permission (Phase 21), so it
    # actually resolves a Principal — unlike a plain read endpoint such as
    # GET /incidents, which never calls get_current_principal at all.
    before = client.get("/api/v1/system/metrics").text

    client.get(
        "/api/v1/fleet/overview",
        headers={"X-Tenant-ID": str(api_tenant.id), "Authorization": "NotBearer garbage"},
    )

    after = client.get("/api/v1/system/metrics").text
    assert "auth_failures_total" in after
    assert after != before
