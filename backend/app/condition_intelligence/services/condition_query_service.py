"""Tenant-scoped, read-only condition-assessment query service — mirrors
`app.ml.services.ml_query_service.MLQueryService`/
`app.state_estimation.services.state_estimation_query_service.StateEstimationQueryService`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.condition_intelligence.repositories.condition_assessment_repository import (
    ConditionAssessmentRepository,
)
from app.domain.models import ConditionAssessment
from app.repositories.machine import MachineRepository


class ConditionQueryMachineNotFoundError(LookupError):
    pass


class ConditionQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self._machines = MachineRepository(session)
        self._assessments = ConditionAssessmentRepository(session)

    async def _require_machine(self, tenant_id: uuid.UUID, machine_id: uuid.UUID) -> None:
        if await self._machines.get(tenant_id, machine_id) is None:
            raise ConditionQueryMachineNotFoundError(str(machine_id))

    async def latest(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> ConditionAssessment | None:
        await self._require_machine(tenant_id, machine_id)
        return await self._assessments.get_latest(tenant_id, machine_id)

    async def history(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        *,
        start: datetime | None,
        end: datetime | None,
        limit: int,
    ) -> list[ConditionAssessment]:
        await self._require_machine(tenant_id, machine_id)
        return await self._assessments.list_for_machine(
            tenant_id, machine_id, start=start, end=end, limit=limit
        )
