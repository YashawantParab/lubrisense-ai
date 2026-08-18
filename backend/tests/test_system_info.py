from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import get_settings


def test_system_info_reflects_configured_settings(client: TestClient) -> None:
    response = client.get("/api/v1/system/info")

    assert response.status_code == 200
    settings = get_settings()
    assert response.json() == {
        "application": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
    }


def test_system_info_does_not_leak_secrets(client: TestClient) -> None:
    response = client.get("/api/v1/system/info")

    body_text = response.text.lower()
    assert "database_url" not in body_text
    assert "redis_url" not in body_text
    assert "password" not in body_text
