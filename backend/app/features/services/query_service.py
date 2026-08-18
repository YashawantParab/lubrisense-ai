"""Tenant-scoped feature-vector query service."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import FeatureVector
from app.features.repositories.feature_repository import FeatureRepository
from app.repositories.machine import MachineRepository


class FeatureVectorNotFoundError(LookupError):
    pass


class FeatureQueryMachineNotFoundError(LookupError):
    pass


class FeatureQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self._machines = MachineRepository(session)
        self._features = FeatureRepository(session)

    async def _require_machine(self, tenant_id: uuid.UUID, machine_id: uuid.UUID) -> None:
        if await self._machines.get(tenant_id, machine_id) is None:
            raise FeatureQueryMachineNotFoundError(str(machine_id))

    async def list_for_machine(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        *,
        feature_set: str | None,
        start: datetime | None,
        end: datetime | None,
        limit: int,
    ) -> list[FeatureVector]:
        await self._require_machine(tenant_id, machine_id)
        return await self._features.list_for_machine(
            tenant_id,
            machine_id,
            feature_set=feature_set,
            start=start,
            end=end,
            limit=limit,
        )

    async def get_vector(self, tenant_id: uuid.UUID, vector_id: uuid.UUID) -> FeatureVector:
        vector = await self._features.get_by_id(tenant_id, vector_id)
        if vector is None:
            raise FeatureVectorNotFoundError(str(vector_id))
        return vector
