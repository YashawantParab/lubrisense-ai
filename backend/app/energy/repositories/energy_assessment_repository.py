"""`EnergyAssessment` repository — tenant-scoped, append-only (mirrors
`app.ml.repositories.ml_repository.MLInferenceResultRepository`: a re-assessment at a
later `as_of_timestamp` is a new row, never an update in place)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select

from app.domain.models import EnergyAssessment
from app.repositories.base import TenantScopedRepository


class EnergyAssessmentRepository(TenantScopedRepository[EnergyAssessment]):
    model = EnergyAssessment

    async def insert(self, assessment: EnergyAssessment) -> EnergyAssessment:
        self.session.add(assessment)
        await self.session.flush()
        return assessment

    async def latest_for_machine(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> EnergyAssessment | None:
        stmt = (
            select(EnergyAssessment)
            .where(
                EnergyAssessment.tenant_id == tenant_id,
                EnergyAssessment.machine_id == machine_id,
            )
            .order_by(EnergyAssessment.as_of_timestamp.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_latest_for_tenant(self, tenant_id: uuid.UUID) -> list[EnergyAssessment]:
        """One row per machine — this machine's most recent persisted assessment,
        fleet-wide. Mirrors `MLInferenceResultRepository.list_latest_for_tenant`, but the
        grain is per-machine (not per-machine-per-model): unlike ML, at most one
        `MACHINE_POWER` sensor is assessed per machine in this pass."""
        latest_per_machine = (
            select(
                EnergyAssessment.machine_id,
                func.max(EnergyAssessment.as_of_timestamp).label("max_ts"),
            )
            .where(EnergyAssessment.tenant_id == tenant_id)
            .group_by(EnergyAssessment.machine_id)
            .subquery()
        )
        result = await self.session.execute(
            select(EnergyAssessment)
            .join(
                latest_per_machine,
                (EnergyAssessment.machine_id == latest_per_machine.c.machine_id)
                & (EnergyAssessment.as_of_timestamp == latest_per_machine.c.max_ts),
            )
            .where(EnergyAssessment.tenant_id == tenant_id)
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
    ) -> list[EnergyAssessment]:
        stmt = select(EnergyAssessment).where(
            EnergyAssessment.tenant_id == tenant_id,
            EnergyAssessment.machine_id == machine_id,
        )
        if start is not None:
            stmt = stmt.where(EnergyAssessment.as_of_timestamp >= start)
        if end is not None:
            stmt = stmt.where(EnergyAssessment.as_of_timestamp <= end)
        stmt = stmt.order_by(EnergyAssessment.as_of_timestamp.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
