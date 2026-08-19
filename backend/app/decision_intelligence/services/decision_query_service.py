"""Tenant-scoped, read-only decision-assessment query service."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.decision_intelligence.repositories.decision_assessment_repository import (
    DecisionAssessmentRepository,
)
from app.domain.models import DecisionAssessment
from app.repositories.machine import MachineRepository


class DecisionQueryMachineNotFoundError(LookupError):
    pass


class DecisionQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self._machines = MachineRepository(session)
        self._decisions = DecisionAssessmentRepository(session)

    async def _require_machine(self, tenant_id: uuid.UUID, machine_id: uuid.UUID) -> None:
        if await self._machines.get(tenant_id, machine_id) is None:
            raise DecisionQueryMachineNotFoundError(str(machine_id))

    async def latest(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> DecisionAssessment | None:
        await self._require_machine(tenant_id, machine_id)
        return await self._decisions.get_latest(tenant_id, machine_id)

    async def history(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        *,
        start: datetime | None,
        end: datetime | None,
        limit: int,
    ) -> list[DecisionAssessment]:
        await self._require_machine(tenant_id, machine_id)
        return await self._decisions.list_for_machine(
            tenant_id, machine_id, start=start, end=end, limit=limit
        )
