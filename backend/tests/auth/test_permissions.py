"""`app.auth` unit tests: token issue/verify round-trip, tampering, expiry, and the
central `AuthorizationService` gate (Phase 24 brief §24.1/§24.4)."""

from __future__ import annotations

import time
import uuid

import pytest

from app.auth.demo_tokens import DemoTokenProvider, InvalidTokenError
from app.auth.models import Principal
from app.auth.permissions import Permission
from app.auth.service import AuthorizationService
from app.core.errors import ApplicationError
from app.domain.enums import UserRole


def _provider(ttl_seconds: int = 3600) -> DemoTokenProvider:
    return DemoTokenProvider(secret="test-secret", ttl_seconds=ttl_seconds)


def test_issue_and_verify_round_trip() -> None:
    tenant_id = uuid.uuid4()
    provider = _provider()
    token = provider.issue(
        user_id="demo-viewer",
        tenant_id=tenant_id,
        role=UserRole.VIEWER,
        display_name="Demo Viewer",
    )
    principal = provider.verify(token)
    assert principal.user_id == "demo-viewer"
    assert principal.tenant_id == tenant_id
    assert principal.role == UserRole.VIEWER


def test_verify_rejects_tampered_signature() -> None:
    provider = _provider()
    token = provider.issue(
        user_id="demo-viewer", tenant_id=uuid.uuid4(), role=UserRole.VIEWER, display_name="x"
    )
    header, payload, _signature = token.split(".")
    tampered = f"{header}.{payload}.not-a-real-signature"
    with pytest.raises(InvalidTokenError):
        provider.verify(tampered)


def test_verify_rejects_token_signed_with_different_secret() -> None:
    token = _provider().issue(
        user_id="demo-viewer", tenant_id=uuid.uuid4(), role=UserRole.VIEWER, display_name="x"
    )
    other_provider = DemoTokenProvider(secret="a-different-secret")
    with pytest.raises(InvalidTokenError):
        other_provider.verify(token)


def test_verify_rejects_expired_token() -> None:
    provider = _provider(ttl_seconds=-1)
    token = provider.issue(
        user_id="demo-viewer", tenant_id=uuid.uuid4(), role=UserRole.VIEWER, display_name="x"
    )
    time.sleep(0.01)
    with pytest.raises(InvalidTokenError, match="expired"):
        provider.verify(token)


def test_verify_rejects_malformed_token() -> None:
    with pytest.raises(InvalidTokenError):
        _provider().verify("not-a-jwt-shaped-token")


@pytest.mark.parametrize(
    ("role", "permission", "allowed"),
    [
        (UserRole.VIEWER, Permission.INCIDENT_READ, True),
        (UserRole.VIEWER, Permission.INCIDENT_MANAGE, False),
        (UserRole.VIEWER, Permission.MAINTENANCE_WRITE, False),
        (UserRole.TECHNICIAN, Permission.MAINTENANCE_WRITE, True),
        (UserRole.TECHNICIAN, Permission.INCIDENT_MANAGE, False),
        (UserRole.RELIABILITY_ENGINEER, Permission.INCIDENT_MANAGE, True),
        (UserRole.RELIABILITY_ENGINEER, Permission.KNOWLEDGE_ADMIN, True),
        (UserRole.PLANT_MANAGER, Permission.INCIDENT_MANAGE, True),
        (UserRole.PLANT_MANAGER, Permission.KNOWLEDGE_ADMIN, False),
        (UserRole.DATA_SCIENTIST, Permission.MAINTENANCE_WRITE, False),
        (UserRole.DATA_SCIENTIST, Permission.AGENT_USE, False),
        (UserRole.DATA_SCIENTIST, Permission.KNOWLEDGE_READ, True),
        (UserRole.ADMIN, Permission.ADMIN_CONFIG, True),
        (UserRole.ADMIN, Permission.KNOWLEDGE_ADMIN, True),
        (UserRole.RELIABILITY_ENGINEER, Permission.ASSET_MANAGE, True),
        (UserRole.PLANT_MANAGER, Permission.ASSET_MANAGE, True),
        (UserRole.VIEWER, Permission.ASSET_MANAGE, False),
        (UserRole.TECHNICIAN, Permission.ASSET_MANAGE, False),
        (UserRole.DATA_SCIENTIST, Permission.ASSET_MANAGE, False),
        (UserRole.ADMIN, Permission.ASSET_MANAGE, True),
    ],
)
def test_authorization_service_matrix(
    role: UserRole, permission: Permission, allowed: bool
) -> None:
    principal = Principal(
        user_id="u", tenant_id=uuid.uuid4(), role=role, display_name="Test"
    )
    if allowed:
        AuthorizationService.require(principal, permission)
    else:
        with pytest.raises(ApplicationError) as exc_info:
            AuthorizationService.require(principal, permission)
        assert exc_info.value.status_code == 403
