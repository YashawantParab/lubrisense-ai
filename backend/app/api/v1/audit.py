"""Tenant-scoped, authorized read access to the append-only audit trail (Phase 25 brief
§25.5). There is no write route here — `AuditEvent` rows are only ever produced as a
side effect of the mutating endpoints/services that call `AuditService.record()`."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session, require_permission
from app.api.schemas.audit import AuditEventResponse
from app.api.schemas.common import PaginatedResponse
from app.audit.repository import AuditEventRepository
from app.auth.permissions import Permission
from app.domain.models import Tenant
from app.repositories.pagination import PageParams
from app.services.errors import NotFoundError

router = APIRouter(prefix="/audit-events", tags=["audit"])


@router.get("", response_model=PaginatedResponse[AuditEventResponse])
async def list_audit_events(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _principal: Annotated[object, require_permission(Permission.AUDIT_READ)],
    actor_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    correlation_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[AuditEventResponse]:
    repo = AuditEventRepository(session)
    page = await repo.search(
        tenant.id,
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        correlation_id=correlation_id,
        since=since,
        until=until,
        params=PageParams(limit=limit, offset=offset),
    )
    items = [AuditEventResponse.model_validate(item) for item in page.items]
    return PaginatedResponse.from_page(page, items)


@router.get("/{audit_event_id}", response_model=AuditEventResponse)
async def get_audit_event(
    audit_event_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _principal: Annotated[object, require_permission(Permission.AUDIT_READ)],
) -> AuditEventResponse:
    repo = AuditEventRepository(session)
    event = await repo.get(tenant.id, audit_event_id)
    if event is None:
        raise NotFoundError("AUDIT_EVENT_NOT_FOUND", "Audit event not found.")
    return AuditEventResponse.model_validate(event)
