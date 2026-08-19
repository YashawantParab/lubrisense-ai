from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select

from app.domain.models import AuditEvent
from app.repositories.base import TenantScopedRepository
from app.repositories.pagination import Page, PageParams


class AuditEventRepository(TenantScopedRepository[AuditEvent]):
    model = AuditEvent

    async def search(
        self,
        tenant_id: uuid.UUID,
        *,
        actor_id: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        action: str | None = None,
        correlation_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        params: PageParams | None = None,
    ) -> Page[AuditEvent]:
        filters = []
        if actor_id is not None:
            filters.append(AuditEvent.actor_id == actor_id)
        if entity_type is not None:
            filters.append(AuditEvent.entity_type == entity_type)
        if entity_id is not None:
            filters.append(AuditEvent.entity_id == entity_id)
        if action is not None:
            filters.append(AuditEvent.action == action)
        if correlation_id is not None:
            filters.append(AuditEvent.correlation_id == correlation_id)
        if since is not None:
            filters.append(AuditEvent.created_at >= since)
        if until is not None:
            filters.append(AuditEvent.created_at <= until)

        params = params or PageParams()
        where_clauses = [AuditEvent.tenant_id == tenant_id, *filters]

        total = await self.session.scalar(
            select(func.count()).select_from(AuditEvent).where(*where_clauses)
        )

        stmt = (
            select(AuditEvent)
            .where(*where_clauses)
            .order_by(AuditEvent.created_at.desc())
            .limit(params.limit)
            .offset(params.offset)
        )
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())
        return Page(items=items, total=total or 0, limit=params.limit, offset=params.offset)
