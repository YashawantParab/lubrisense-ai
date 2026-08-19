"""`IncidentEvent` repository — tenant-scoped, append-only (Phase 16 brief §16.8)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import IncidentEvent


class IncidentEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert(self, event: IncidentEvent) -> IncidentEvent:
        self.session.add(event)
        await self.session.flush()
        await self.session.refresh(event)
        return event

    async def list_for_incident(
        self, tenant_id: uuid.UUID, incident_id: uuid.UUID
    ) -> list[IncidentEvent]:
        result = await self.session.execute(
            select(IncidentEvent)
            .where(IncidentEvent.tenant_id == tenant_id, IncidentEvent.incident_id == incident_id)
            .order_by(IncidentEvent.recorded_at.asc())
        )
        return list(result.scalars().all())
