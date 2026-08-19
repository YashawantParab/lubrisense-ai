"""`MaintenanceAction` repository — tenant-scoped, append-only."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import MaintenanceAction


class MaintenanceActionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert(self, action: MaintenanceAction) -> MaintenanceAction:
        self.session.add(action)
        await self.session.flush()
        await self.session.refresh(action)
        return action

    async def list_for_case(
        self, tenant_id: uuid.UUID, maintenance_case_id: uuid.UUID
    ) -> list[MaintenanceAction]:
        result = await self.session.execute(
            select(MaintenanceAction)
            .where(
                MaintenanceAction.tenant_id == tenant_id,
                MaintenanceAction.maintenance_case_id == maintenance_case_id,
            )
            .order_by(MaintenanceAction.recorded_at.asc())
        )
        return list(result.scalars().all())
