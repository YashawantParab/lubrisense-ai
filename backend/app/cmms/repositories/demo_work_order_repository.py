"""`DemoCMMSWorkOrder` repository — tenant-scoped."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import DemoCMMSWorkOrder


class DemoCMMSWorkOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert(self, work_order: DemoCMMSWorkOrder) -> DemoCMMSWorkOrder:
        self.session.add(work_order)
        await self.session.flush()
        await self.session.refresh(work_order)
        return work_order

    async def save(self, work_order: DemoCMMSWorkOrder) -> DemoCMMSWorkOrder:
        await self.session.flush()
        await self.session.refresh(work_order)
        return work_order

    async def get_for_case(
        self, tenant_id: uuid.UUID, maintenance_case_id: uuid.UUID
    ) -> DemoCMMSWorkOrder | None:
        result = await self.session.execute(
            select(DemoCMMSWorkOrder).where(
                DemoCMMSWorkOrder.tenant_id == tenant_id,
                DemoCMMSWorkOrder.maintenance_case_id == maintenance_case_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_external_reference(
        self, tenant_id: uuid.UUID, external_reference: str
    ) -> DemoCMMSWorkOrder | None:
        result = await self.session.execute(
            select(DemoCMMSWorkOrder).where(
                DemoCMMSWorkOrder.tenant_id == tenant_id,
                DemoCMMSWorkOrder.external_reference == external_reference,
            )
        )
        return result.scalar_one_or_none()
