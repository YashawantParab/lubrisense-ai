"""`LubricationEnergyAttribution` repository — tenant-scoped, append-only (mirrors
`app.energy.repositories.energy_assessment_repository.EnergyAssessmentRepository`)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select

from app.domain.models import LubricationEnergyAttribution
from app.repositories.base import TenantScopedRepository


class AttributionRepository(TenantScopedRepository[LubricationEnergyAttribution]):
    model = LubricationEnergyAttribution

    async def insert(
        self, attribution: LubricationEnergyAttribution
    ) -> LubricationEnergyAttribution:
        self.session.add(attribution)
        await self.session.flush()
        return attribution

    async def latest_for_machine(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> LubricationEnergyAttribution | None:
        stmt = (
            select(LubricationEnergyAttribution)
            .where(
                LubricationEnergyAttribution.tenant_id == tenant_id,
                LubricationEnergyAttribution.machine_id == machine_id,
            )
            .order_by(LubricationEnergyAttribution.as_of_timestamp.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_latest_for_tenant(
        self, tenant_id: uuid.UUID
    ) -> list[LubricationEnergyAttribution]:
        latest_per_machine = (
            select(
                LubricationEnergyAttribution.machine_id,
                func.max(LubricationEnergyAttribution.as_of_timestamp).label("max_ts"),
            )
            .where(LubricationEnergyAttribution.tenant_id == tenant_id)
            .group_by(LubricationEnergyAttribution.machine_id)
            .subquery()
        )
        result = await self.session.execute(
            select(LubricationEnergyAttribution)
            .join(
                latest_per_machine,
                (LubricationEnergyAttribution.machine_id == latest_per_machine.c.machine_id)
                & (LubricationEnergyAttribution.as_of_timestamp == latest_per_machine.c.max_ts),
            )
            .where(LubricationEnergyAttribution.tenant_id == tenant_id)
        )
        return list(result.scalars().unique().all())

    async def list_for_machine(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        *,
        start: datetime | None,
        end: datetime | None,
        limit: int,
    ) -> list[LubricationEnergyAttribution]:
        stmt = select(LubricationEnergyAttribution).where(
            LubricationEnergyAttribution.tenant_id == tenant_id,
            LubricationEnergyAttribution.machine_id == machine_id,
        )
        if start is not None:
            stmt = stmt.where(LubricationEnergyAttribution.as_of_timestamp >= start)
        if end is not None:
            stmt = stmt.where(LubricationEnergyAttribution.as_of_timestamp <= end)
        stmt = stmt.order_by(LubricationEnergyAttribution.as_of_timestamp.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
