"""`Settings.model_post_init`'s fail-fast safety validation (Phase 23 brief §23.7),
extended to also cover `hosted_demo` (docs/HOSTED_DEPLOYMENT.md) — a publicly reachable
deployment carries the same auth/CORS/secret risk surface as `production` even though it
is explicitly not a claim of real industrial deployment readiness."""

from __future__ import annotations

import pytest

from app.core.config import Settings


@pytest.mark.parametrize("app_env", ["production", "hosted_demo"])
def test_strict_environments_reject_permissive_auth(
    monkeypatch: pytest.MonkeyPatch, app_env: str
) -> None:
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("AUTH_ENFORCEMENT_MODE", "permissive")
    monkeypatch.setenv("DEMO_AUTH_SECRET", "a-real-overridden-secret")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://example.com")
    monkeypatch.setenv("TRUSTED_HOSTS", "example.com")
    with pytest.raises(ValueError, match="AUTH_ENFORCEMENT_MODE must be 'strict'"):
        Settings()


@pytest.mark.parametrize("app_env", ["production", "hosted_demo"])
def test_strict_environments_reject_default_demo_auth_secret(
    monkeypatch: pytest.MonkeyPatch, app_env: str
) -> None:
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("AUTH_ENFORCEMENT_MODE", "strict")
    monkeypatch.delenv("DEMO_AUTH_SECRET", raising=False)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://example.com")
    monkeypatch.setenv("TRUSTED_HOSTS", "example.com")
    with pytest.raises(ValueError, match="DEMO_AUTH_SECRET must be overridden"):
        Settings()


@pytest.mark.parametrize("app_env", ["production", "hosted_demo"])
def test_strict_environments_reject_wildcard_cors(
    monkeypatch: pytest.MonkeyPatch, app_env: str
) -> None:
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("AUTH_ENFORCEMENT_MODE", "strict")
    monkeypatch.setenv("DEMO_AUTH_SECRET", "a-real-overridden-secret")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")
    monkeypatch.setenv("TRUSTED_HOSTS", "example.com")
    with pytest.raises(ValueError, match="CORS_ALLOWED_ORIGINS must not be '\\*'"):
        Settings()


@pytest.mark.parametrize("app_env", ["production", "hosted_demo"])
def test_strict_environments_reject_wildcard_trusted_hosts(
    monkeypatch: pytest.MonkeyPatch, app_env: str
) -> None:
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("AUTH_ENFORCEMENT_MODE", "strict")
    monkeypatch.setenv("DEMO_AUTH_SECRET", "a-real-overridden-secret")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://example.com")
    monkeypatch.setenv("TRUSTED_HOSTS", "*")
    with pytest.raises(ValueError, match="TRUSTED_HOSTS must not be '\\*'"):
        Settings()


@pytest.mark.parametrize("app_env", ["production", "hosted_demo"])
def test_strict_environments_accept_a_fully_safe_configuration(
    monkeypatch: pytest.MonkeyPatch, app_env: str
) -> None:
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("AUTH_ENFORCEMENT_MODE", "strict")
    monkeypatch.setenv("DEMO_AUTH_SECRET", "a-real-overridden-secret")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://example.com")
    monkeypatch.setenv("TRUSTED_HOSTS", "example.com")
    settings = Settings()
    assert settings.app_env == app_env


@pytest.mark.parametrize("app_env", ["local", "development", "staging"])
def test_non_strict_environments_allow_permissive_defaults(
    monkeypatch: pytest.MonkeyPatch, app_env: str
) -> None:
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.delenv("AUTH_ENFORCEMENT_MODE", raising=False)
    monkeypatch.delenv("DEMO_AUTH_SECRET", raising=False)
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("TRUSTED_HOSTS", raising=False)
    settings = Settings()
    assert settings.auth_enforcement_mode == "permissive"


def test_is_production_is_true_only_for_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """`hosted_demo` shares production's *safety* checks but must not be conflated with
    a real industrial-production claim (CLAUDE.md's Industrial Adoption Boundary,
    docs/INDUSTRIAL_ADOPTION.md) — `is_production` stays literal."""
    monkeypatch.setenv("APP_ENV", "hosted_demo")
    monkeypatch.setenv("AUTH_ENFORCEMENT_MODE", "strict")
    monkeypatch.setenv("DEMO_AUTH_SECRET", "a-real-overridden-secret")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://example.com")
    monkeypatch.setenv("TRUSTED_HOSTS", "example.com")
    assert Settings().is_production is False
