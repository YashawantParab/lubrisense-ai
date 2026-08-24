"""Tenant-scoped, read-only energy-assessment query service — mirrors
`app.ml.services.ml_query_service.MLQueryService` (never triggers computation; that only
ever happens via `EnergyAssessmentService`, on-demand)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import EnergyAssessment
from app.energy.repositories.energy_assessment_repository import EnergyAssessmentRepository
from app.repositories.machine import MachineRepository


class EnergyQueryMachineNotFoundError(LookupError):
    pass


class EnergyQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self._machines = MachineRepository(session)
        self._assessments = EnergyAssessmentRepository(session)

    async def _require_machine(self, tenant_id: uuid.UUID, machine_id: uuid.UUID) -> None:
        if await self._machines.get(tenant_id, machine_id) is None:
            raise EnergyQueryMachineNotFoundError(str(machine_id))

    async def latest(self, tenant_id: uuid.UUID, machine_id: uuid.UUID) -> EnergyAssessment | None:
        await self._require_machine(tenant_id, machine_id)
        return await self._assessments.latest_for_machine(tenant_id, machine_id)

    async def fleet_latest(self, tenant_id: uuid.UUID) -> list[EnergyAssessment]:
        return await self._assessments.list_latest_for_tenant(tenant_id)

    async def history(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        *,
        start: datetime | None,
        end: datetime | None,
        limit: int,
    ) -> list[EnergyAssessment]:
        await self._require_machine(tenant_id, machine_id)
        return await self._assessments.list_for_machine(
            tenant_id, machine_id, start=start, end=end, limit=limit
        )
