"""Tenant-scoped, read-only state-estimate query service — mirrors
`app.ml.services.ml_query_service.MLQueryService`."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import StateEstimate
from app.repositories.machine import MachineRepository
from app.state_estimation.repositories.state_estimate_repository import StateEstimateRepository


class StateEstimationQueryMachineNotFoundError(LookupError):
    pass


class StateEstimationQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self._machines = MachineRepository(session)
        self._estimates = StateEstimateRepository(session)

    async def _require_machine(self, tenant_id: uuid.UUID, machine_id: uuid.UUID) -> None:
        if await self._machines.get(tenant_id, machine_id) is None:
            raise StateEstimationQueryMachineNotFoundError(str(machine_id))

    async def latest(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID, state_type: str, estimator_version: str
    ) -> StateEstimate | None:
        await self._require_machine(tenant_id, machine_id)
        return await self._estimates.get_latest(
            tenant_id, machine_id, state_type, estimator_version
        )

    async def history(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        *,
        state_type: str | None,
        start: datetime | None,
        end: datetime | None,
        limit: int,
    ) -> list[StateEstimate]:
        await self._require_machine(tenant_id, machine_id)
        return await self._estimates.list_for_machine(
            tenant_id, machine_id, state_type=state_type, start=start, end=end, limit=limit
        )
