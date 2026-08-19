from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.services.health_service import check_readiness


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
    # Local/full-stack: both dependencies are required, matching pre-existing behavior.
    assert all(dep["required"] for dep in body["dependencies"])
    assert all(dep["status"] == "healthy" for dep in body["dependencies"])


class _FakeDatabase:
    def __init__(self, healthy: bool) -> None:
        self._healthy = healthy

    async def check_connection(self) -> bool:
        return self._healthy


class _FakeRedisClient:
    def __init__(self, healthy: bool) -> None:
        self._healthy = healthy

    async def check_connection(self) -> bool:
        return self._healthy


def _settings(app_env: str, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Build a `Settings` instance for `app_env`, satisfying `model_post_init`'s
    fail-fast safety checks for the strict environments (production/hosted_demo) the
    same way `test_config.py` does."""
    monkeypatch.setenv("APP_ENV", app_env)
    if app_env in ("production", "hosted_demo"):
        monkeypatch.setenv("AUTH_ENFORCEMENT_MODE", "strict")
        monkeypatch.setenv("DEMO_AUTH_SECRET", "a-real-overridden-secret")
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://example.com")
        monkeypatch.setenv("TRUSTED_HOSTS", "example.com")
    return Settings()


@pytest.mark.asyncio
async def test_hosted_demo_ready_with_healthy_database_and_no_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings("hosted_demo", monkeypatch)

    result = await check_readiness(
        _FakeDatabase(healthy=True),  # type: ignore[arg-type]
        _FakeRedisClient(healthy=False),  # type: ignore[arg-type]
        settings,
    )

    assert result.ready is True
    redis_status = next(dep for dep in result.dependencies if dep.name == "redis")
    assert redis_status.required is False
    # Not falsely healthy: Redis is genuinely unreachable, just not load-bearing.
    assert redis_status.healthy is False


@pytest.mark.asyncio
async def test_hosted_demo_not_ready_with_unhealthy_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings("hosted_demo", monkeypatch)

    result = await check_readiness(
        _FakeDatabase(healthy=False),  # type: ignore[arg-type]
        _FakeRedisClient(healthy=False),  # type: ignore[arg-type]
        settings,
    )

    assert result.ready is False
    database_status = next(dep for dep in result.dependencies if dep.name == "database")
    assert database_status.required is True
    assert database_status.healthy is False


@pytest.mark.parametrize("app_env", ["local", "development", "staging", "production"])
@pytest.mark.asyncio
async def test_non_hosted_demo_environments_still_require_redis(
    monkeypatch: pytest.MonkeyPatch, app_env: str
) -> None:
    """Local/full-stack (and every other non-`hosted_demo` environment) behavior is
    unchanged: Redis remains required, so an unreachable Redis still fails readiness."""
    settings = _settings(app_env, monkeypatch)

    result = await check_readiness(
        _FakeDatabase(healthy=True),  # type: ignore[arg-type]
        _FakeRedisClient(healthy=False),  # type: ignore[arg-type]
        settings,
    )

    assert result.ready is False
    redis_status = next(dep for dep in result.dependencies if dep.name == "redis")
    assert redis_status.required is True
    assert redis_status.healthy is False


@pytest.mark.asyncio
async def test_unreachable_optional_redis_is_never_reported_as_healthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings("hosted_demo", monkeypatch)

    result = await check_readiness(
        _FakeDatabase(healthy=True),  # type: ignore[arg-type]
        _FakeRedisClient(healthy=False),  # type: ignore[arg-type]
        settings,
    )

    redis_status = next(dep for dep in result.dependencies if dep.name == "redis")
    assert redis_status.healthy is False
    assert redis_status.required is False
