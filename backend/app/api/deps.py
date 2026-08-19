"""FastAPI dependency providers shared across route modules.

Includes the Phase 2 tenant-context mechanism — see `get_current_tenant` below for why it
exists and why it is explicitly a development-only stand-in for real authentication.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import Depends, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.demo_tokens import DemoTokenProvider, InvalidTokenError
from app.auth.models import Principal
from app.auth.permissions import Permission
from app.auth.service import AuthorizationService
from app.core.config import Settings, get_settings
from app.core.errors import ApplicationError
from app.domain.enums import AuditActorType, TenantStatus, UserRole
from app.domain.models import Tenant
from app.infrastructure.database import Database
from app.infrastructure.redis_client import RedisClient
from app.observability.http_metrics import HTTP_METRICS
from app.repositories.tenant import TenantRepository

TENANT_HEADER = "X-Tenant-ID"
_FALLBACK_PRINCIPAL_USER_ID = "pre-auth-compat-principal"


def get_app_settings() -> Settings:
    return get_settings()


def get_database(request: Request) -> Database:
    return request.app.state.database  # type: ignore[no-any-return]


def get_redis_client(request: Request) -> RedisClient:
    return request.app.state.redis_client  # type: ignore[no-any-return]


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """One AsyncSession per request, committed on success and rolled back on error.

    Route handlers never open a session directly — only through this dependency (and
    thereby only through a repository/service built on it).
    """
    database: Database = request.app.state.database
    async with database.session() as session:
        yield session
        await session.commit()


async def get_tenant_id_header(
    x_tenant_id: Annotated[str | None, Header(alias=TENANT_HEADER)] = None,
) -> uuid.UUID:
    """Parses the `X-Tenant-ID` header. Format validation only — see `get_current_tenant`
    for the existence/status check that actually establishes tenant context."""
    if not x_tenant_id:
        raise ApplicationError(
            "TENANT_CONTEXT_REQUIRED",
            f"Missing required '{TENANT_HEADER}' header.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        return uuid.UUID(x_tenant_id)
    except ValueError as exc:
        raise ApplicationError(
            "TENANT_CONTEXT_INVALID",
            f"'{TENANT_HEADER}' header must be a valid UUID.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc


async def get_current_tenant(
    tenant_id: Annotated[uuid.UUID, Depends(get_tenant_id_header)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Tenant:
    """Resolves and validates the tenant for this request from the `X-Tenant-ID` header.

    *** DEVELOPMENT-ONLY. NOT AUTHENTICATION. ***

    Phase 2 has no authentication/RBAC yet (LOOP.md explicitly defers it). Every API
    request must still carry an explicit, validated tenant context — see
    `docs/ASSET_HIERARCHY.md` §"Tenant context" and TECHNICAL_DECISIONS.md
    (tenant-context-before-authentication ADR). This function is the single seam that
    will be replaced: a real implementation extracts `tenant_id` from a verified JWT/OIDC
    claim instead of trusting a client-supplied header, then performs the same
    existence/status check below. Nothing downstream of this dependency (services,
    repositories) needs to change when that happens — they only ever see a validated
    `tenant_id`/`Tenant`, never the header itself.
    """
    tenant = await TenantRepository(session).get(tenant_id)
    if tenant is None:
        raise ApplicationError(
            "TENANT_NOT_FOUND", "Unknown tenant.", status_code=status.HTTP_404_NOT_FOUND
        )
    if tenant.status != TenantStatus.ACTIVE:
        raise ApplicationError(
            "TENANT_INACTIVE", "Tenant is not active.", status_code=status.HTTP_403_FORBIDDEN
        )
    return tenant


async def get_current_principal(
    request: Request,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> Principal:
    """Resolves the authenticated `Principal` for this request from an `Authorization:
    Bearer <demo-token>` header, verified against `Settings.demo_auth_secret` (see
    `app.auth.demo_tokens.DemoTokenProvider`).

    *** DEMO AUTH BOUNDARY *** — see `docs/SECURITY.md`. When no token is presented:

    - `AUTH_ENFORCEMENT_MODE=strict` (required in production, see
      `Settings.model_post_init`): the request is rejected with 401.
    - `AUTH_ENFORCEMENT_MODE=permissive` (the local/demo default): a full-access
      fallback principal is returned, bound to the already-validated tenant. This is
      what preserves backward compatibility with every pre-Phase-24 API caller — this
      repository's own pre-Phase-24 test suite included — none of which ever sends an
      Authorization header. It is not a bypass for a caller that *does* present a
      token: a token whose `tenant_id` claim does not match the resolved tenant is
      always rejected (403), in both modes.
    """
    authorization = request.headers.get("Authorization")
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            HTTP_METRICS.increment("auth_failures_total")
            raise ApplicationError(
                "AUTH_HEADER_MALFORMED",
                "Authorization header must be 'Bearer <token>'.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        provider = DemoTokenProvider(
            secret=settings.demo_auth_secret, ttl_seconds=settings.demo_token_ttl_seconds
        )
        try:
            principal = provider.verify(token)
        except InvalidTokenError as exc:
            HTTP_METRICS.increment("auth_failures_total")
            raise ApplicationError(
                "AUTH_TOKEN_INVALID", str(exc), status_code=status.HTTP_401_UNAUTHORIZED
            ) from exc
        if principal.tenant_id != tenant.id:
            HTTP_METRICS.increment("auth_failures_total")
            raise ApplicationError(
                "AUTH_TENANT_MISMATCH",
                "Token tenant does not match the requested tenant context.",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        return principal

    if settings.auth_enforcement_mode == "strict":
        HTTP_METRICS.increment("auth_failures_total")
        raise ApplicationError(
            "AUTH_REQUIRED",
            "An 'Authorization: Bearer <token>' header is required.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    return Principal(
        user_id=_FALLBACK_PRINCIPAL_USER_ID,
        tenant_id=tenant.id,
        role=UserRole.ADMIN,
        display_name="Pre-auth compatibility principal",
        actor_type=AuditActorType.HUMAN,
    )


def require_permission(
    permission: Permission,
) -> Any:
    """A FastAPI dependency factory: `Depends(require_permission(Permission.X))`
    resolves the current principal and raises 403 if it lacks `permission` (Phase 24
    brief §24.4/§24.7). Returns the `Principal` on success so route handlers that need
    the caller's identity (e.g. for `AuditService.record`) do not need a second
    dependency."""

    async def _check(
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        AuthorizationService.require(principal, permission)
        return principal

    return Depends(_check)
