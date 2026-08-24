"""Tenant-scoped, read-only carbon query service — mirrors
`app.energy.services.energy_outcome_query_service.EnergyOutcomeQueryService` (never
triggers computation; that only ever happens via `CarbonService`, on-demand)."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import CarbonImpactEstimate
from app.energy.repositories.carbon_estimate_repository import CarbonEstimateRepository
from app.repositories.machine import MachineRepository


class CarbonQueryMachineNotFoundError(LookupError):
    pass


class CarbonQueryEstimateNotFoundError(LookupError):
    pass


class CarbonQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self._machines = MachineRepository(session)
        self._estimates = CarbonEstimateRepository(session)

    async def get(self, tenant_id: uuid.UUID, estimate_id: uuid.UUID) -> CarbonImpactEstimate:
        estimate = await self._estimates.get(tenant_id, estimate_id)
        if estimate is None:
            raise CarbonQueryEstimateNotFoundError(str(estimate_id))
        return estimate

    async def latest_for_machine(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> CarbonImpactEstimate | None:
        if await self._machines.get(tenant_id, machine_id) is None:
            raise CarbonQueryMachineNotFoundError(str(machine_id))
        return await self._estimates.latest_for_machine(tenant_id, machine_id)

    async def fleet_latest(self, tenant_id: uuid.UUID) -> list[CarbonImpactEstimate]:
        return await self._estimates.list_latest_for_tenant(tenant_id)
