from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_reports_healthy_dependencies(client: TestClient) -> None:
    response = client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"

    dependency_names = {dep["name"] for dep in body["dependencies"]}
    assert dependency_names == {"database", "redis"}
    assert all(dep["healthy"] for dep in body["dependencies"])
