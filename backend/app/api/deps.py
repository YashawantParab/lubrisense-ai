"""FastAPI dependency providers shared across route modules.

Includes the Phase 2 tenant-context mechanism — see `get_current_tenant` below for why it
exists and why it is explicitly a development-only stand-in for real authentication.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import ApplicationError
from app.domain.enums import TenantStatus
from app.domain.models import Tenant
from app.infrastructure.database import Database
from app.infrastructure.redis_client import RedisClient
from app.repositories.tenant import TenantRepository

TENANT_HEADER = "X-Tenant-ID"


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
