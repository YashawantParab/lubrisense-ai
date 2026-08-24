"""`CarbonImpactEstimate` repository — tenant-scoped, append-only (mirrors
`app.energy.repositories.energy_outcome_repository.EnergyOutcomeRepository`;
Lubrication Efficiency Intelligence, Pass 4, ADR-176)."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.domain.models import CarbonImpactEstimate
from app.repositories.base import TenantScopedRepository


class CarbonEstimateRepository(TenantScopedRepository[CarbonImpactEstimate]):
    model = CarbonImpactEstimate

    async def insert(self, estimate: CarbonImpactEstimate) -> CarbonImpactEstimate:
        self.session.add(estimate)
        await self.session.flush()
        return estimate

    async def get(
        self, tenant_id: uuid.UUID, estimate_id: uuid.UUID
    ) -> CarbonImpactEstimate | None:
        stmt = select(CarbonImpactEstimate).where(
            CarbonImpactEstimate.tenant_id == tenant_id, CarbonImpactEstimate.id == estimate_id
        )
        result: CarbonImpactEstimate | None = await self.session.scalar(stmt)
        return result

    async def latest_for_machine(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> CarbonImpactEstimate | None:
        stmt = (
            select(CarbonImpactEstimate)
            .where(
                CarbonImpactEstimate.tenant_id == tenant_id,
                CarbonImpactEstimate.machine_id == machine_id,
            )
            .order_by(CarbonImpactEstimate.created_at.desc())
            .limit(1)
        )
        result: CarbonImpactEstimate | None = await self.session.scalar(stmt)
        return result

    async def latest_for_energy_outcome(
        self, tenant_id: uuid.UUID, energy_outcome_verification_id: uuid.UUID
    ) -> CarbonImpactEstimate | None:
        stmt = (
            select(CarbonImpactEstimate)
            .where(
                CarbonImpactEstimate.tenant_id == tenant_id,
                CarbonImpactEstimate.energy_outcome_verification_id
                == energy_outcome_verification_id,
            )
            .order_by(CarbonImpactEstimate.created_at.desc())
            .limit(1)
        )
        result: CarbonImpactEstimate | None = await self.session.scalar(stmt)
        return result

    async def list_latest_for_tenant(self, tenant_id: uuid.UUID) -> list[CarbonImpactEstimate]:
        latest_per_machine = (
            select(
                CarbonImpactEstimate.machine_id,
                func.max(CarbonImpactEstimate.created_at).label("max_ts"),
            )
            .where(CarbonImpactEstimate.tenant_id == tenant_id)
            .group_by(CarbonImpactEstimate.machine_id)
            .subquery()
        )
        result = await self.session.execute(
            select(CarbonImpactEstimate)
            .join(
                latest_per_machine,
                (CarbonImpactEstimate.machine_id == latest_per_machine.c.machine_id)
                & (CarbonImpactEstimate.created_at == latest_per_machine.c.max_ts),
            )
            .where(CarbonImpactEstimate.tenant_id == tenant_id)
        )
        return list(result.scalars().unique().all())
