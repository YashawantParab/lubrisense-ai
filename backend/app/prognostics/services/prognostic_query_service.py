"""Tenant-scoped, read-only prognostic-assessment query service."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import PrognosticAssessment
from app.prognostics.repositories.prognostic_assessment_repository import (
    PrognosticAssessmentRepository,
)
from app.repositories.machine import MachineRepository


class PrognosticQueryMachineNotFoundError(LookupError):
    pass


class PrognosticQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self._machines = MachineRepository(session)
        self._assessments = PrognosticAssessmentRepository(session)

    async def _require_machine(self, tenant_id: uuid.UUID, machine_id: uuid.UUID) -> None:
        if await self._machines.get(tenant_id, machine_id) is None:
            raise PrognosticQueryMachineNotFoundError(str(machine_id))

    async def latest(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> list[PrognosticAssessment]:
        await self._require_machine(tenant_id, machine_id)
        return await self._assessments.list_latest_for_machine(tenant_id, machine_id)

    async def history(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        *,
        state_type: str | None,
        start: datetime | None,
        end: datetime | None,
        limit: int,
    ) -> list[PrognosticAssessment]:
        await self._require_machine(tenant_id, machine_id)
        return await self._assessments.list_for_machine(
            tenant_id, machine_id, state_type=state_type, start=start, end=end, limit=limit
        )
