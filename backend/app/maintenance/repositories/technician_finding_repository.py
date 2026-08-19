"""`TechnicianFinding` repository — tenant-scoped, append-only."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import TechnicianFinding


class TechnicianFindingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert(self, finding: TechnicianFinding) -> TechnicianFinding:
        self.session.add(finding)
        await self.session.flush()
        await self.session.refresh(finding)
        return finding

    async def list_for_case(
        self, tenant_id: uuid.UUID, maintenance_case_id: uuid.UUID
    ) -> list[TechnicianFinding]:
        result = await self.session.execute(
            select(TechnicianFinding)
            .where(
                TechnicianFinding.tenant_id == tenant_id,
                TechnicianFinding.maintenance_case_id == maintenance_case_id,
            )
            .order_by(TechnicianFinding.recorded_at.asc())
        )
        return list(result.scalars().all())
