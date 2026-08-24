"""`EnergyOutcomeVerification` repository — tenant-scoped, append-only (mirrors
`app.energy.repositories.attribution_repository.AttributionRepository`; ordered by
`created_at`, when the verification was computed, rather than an `as_of_timestamp` —
this table's own point-in-time anchor is `intervention_timestamp`, which does not change
between recomputations of the same maintenance case)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select

from app.domain.models import EnergyOutcomeVerification
from app.repositories.base import TenantScopedRepository


class EnergyOutcomeRepository(TenantScopedRepository[EnergyOutcomeVerification]):
    model = EnergyOutcomeVerification

    async def insert(self, verification: EnergyOutcomeVerification) -> EnergyOutcomeVerification:
        self.session.add(verification)
        await self.session.flush()
        return verification

    async def latest_for_machine(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> EnergyOutcomeVerification | None:
        stmt = (
            select(EnergyOutcomeVerification)
            .where(
                EnergyOutcomeVerification.tenant_id == tenant_id,
                EnergyOutcomeVerification.machine_id == machine_id,
            )
            .order_by(EnergyOutcomeVerification.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def latest_for_maintenance_case(
        self, tenant_id: uuid.UUID, maintenance_case_id: uuid.UUID
    ) -> EnergyOutcomeVerification | None:
        stmt = (
            select(EnergyOutcomeVerification)
            .where(
                EnergyOutcomeVerification.tenant_id == tenant_id,
                EnergyOutcomeVerification.maintenance_case_id == maintenance_case_id,
            )
            .order_by(EnergyOutcomeVerification.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get(
        self, tenant_id: uuid.UUID, verification_id: uuid.UUID
    ) -> EnergyOutcomeVerification | None:
        stmt = select(EnergyOutcomeVerification).where(
            EnergyOutcomeVerification.tenant_id == tenant_id,
            EnergyOutcomeVerification.id == verification_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_latest_for_tenant(self, tenant_id: uuid.UUID) -> list[EnergyOutcomeVerification]:
        latest_per_machine = (
            select(
                EnergyOutcomeVerification.machine_id,
                func.max(EnergyOutcomeVerification.created_at).label("max_ts"),
            )
            .where(EnergyOutcomeVerification.tenant_id == tenant_id)
            .group_by(EnergyOutcomeVerification.machine_id)
            .subquery()
        )
        result = await self.session.execute(
            select(EnergyOutcomeVerification)
            .join(
                latest_per_machine,
                (EnergyOutcomeVerification.machine_id == latest_per_machine.c.machine_id)
                & (EnergyOutcomeVerification.created_at == latest_per_machine.c.max_ts),
            )
            .where(EnergyOutcomeVerification.tenant_id == tenant_id)
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
    ) -> list[EnergyOutcomeVerification]:
        stmt = select(EnergyOutcomeVerification).where(
            EnergyOutcomeVerification.tenant_id == tenant_id,
            EnergyOutcomeVerification.machine_id == machine_id,
        )
        if start is not None:
            stmt = stmt.where(EnergyOutcomeVerification.created_at >= start)
        if end is not None:
            stmt = stmt.where(EnergyOutcomeVerification.created_at <= end)
        stmt = stmt.order_by(EnergyOutcomeVerification.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
