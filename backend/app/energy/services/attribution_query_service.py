"""Tenant-scoped, read-only attribution query service — mirrors
`app.energy.services.energy_query_service.EnergyQueryService` (never triggers
computation; that only ever happens via `AttributionService`, on-demand)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import LubricationEnergyAttribution
from app.energy.repositories.attribution_repository import AttributionRepository
from app.repositories.machine import MachineRepository


class AttributionQueryMachineNotFoundError(LookupError):
    pass


class AttributionQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self._machines = MachineRepository(session)
        self._attributions = AttributionRepository(session)

    async def _require_machine(self, tenant_id: uuid.UUID, machine_id: uuid.UUID) -> None:
        if await self._machines.get(tenant_id, machine_id) is None:
            raise AttributionQueryMachineNotFoundError(str(machine_id))

    async def latest(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> LubricationEnergyAttribution | None:
        await self._require_machine(tenant_id, machine_id)
        return await self._attributions.latest_for_machine(tenant_id, machine_id)

    async def fleet_latest(self, tenant_id: uuid.UUID) -> list[LubricationEnergyAttribution]:
        return await self._attributions.list_latest_for_tenant(tenant_id)

    async def history(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        *,
        start: datetime | None,
        end: datetime | None,
        limit: int,
    ) -> list[LubricationEnergyAttribution]:
        await self._require_machine(tenant_id, machine_id)
        return await self._attributions.list_for_machine(
            tenant_id, machine_id, start=start, end=end, limit=limit
        )
