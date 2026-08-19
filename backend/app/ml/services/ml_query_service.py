"""Tenant-scoped, read-only ML result query service — mirrors
`app.features.services.query_service.FeatureQueryService`."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import MLInferenceResult
from app.ml.repositories.ml_repository import MLInferenceResultRepository
from app.repositories.machine import MachineRepository


class MLQueryMachineNotFoundError(LookupError):
    pass


class MLQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self._machines = MachineRepository(session)
        self._results = MLInferenceResultRepository(session)

    async def _require_machine(self, tenant_id: uuid.UUID, machine_id: uuid.UUID) -> None:
        if await self._machines.get(tenant_id, machine_id) is None:
            raise MLQueryMachineNotFoundError(str(machine_id))

    async def latest(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID, model_id: str
    ) -> MLInferenceResult | None:
        await self._require_machine(tenant_id, machine_id)
        return await self._results.latest_for_machine(tenant_id, machine_id, model_id)

    async def history(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        *,
        model_id: str | None,
        start: datetime | None,
        end: datetime | None,
        limit: int,
    ) -> list[MLInferenceResult]:
        await self._require_machine(tenant_id, machine_id)
        return await self._results.list_for_machine(
            tenant_id, machine_id, model_id=model_id, start=start, end=end, limit=limit
        )
