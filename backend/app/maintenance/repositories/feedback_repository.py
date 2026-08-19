"""`FeedbackRecord` repository — tenant-scoped."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import FeedbackRecord


class FeedbackRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert(self, record: FeedbackRecord) -> FeedbackRecord:
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def get_for_case(
        self, tenant_id: uuid.UUID, maintenance_case_id: uuid.UUID
    ) -> FeedbackRecord | None:
        result = await self.session.execute(
            select(FeedbackRecord)
            .where(
                FeedbackRecord.tenant_id == tenant_id,
                FeedbackRecord.maintenance_case_id == maintenance_case_id,
            )
            .order_by(FeedbackRecord.recorded_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_for_tenant(
        self, tenant_id: uuid.UUID, *, limit: int = 200
    ) -> list[FeedbackRecord]:
        result = await self.session.execute(
            select(FeedbackRecord)
            .where(FeedbackRecord.tenant_id == tenant_id)
            .order_by(FeedbackRecord.recorded_at.desc())
            .limit(min(limit, 1000))
        )
        return list(result.scalars().all())
