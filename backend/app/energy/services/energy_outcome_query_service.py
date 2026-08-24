"""Tenant-scoped, read-only energy-outcome query service — mirrors
`app.energy.services.attribution_query_service.AttributionQueryService` (never triggers
computation; that only ever happens via `EnergyOutcomeService`, on-demand)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import EnergyOutcomeVerification
from app.energy.repositories.energy_outcome_repository import EnergyOutcomeRepository
from app.repositories.machine import MachineRepository


class EnergyOutcomeQueryMachineNotFoundError(LookupError):
    pass


class EnergyOutcomeQueryVerificationNotFoundError(LookupError):
    pass


class EnergyOutcomeQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self._machines = MachineRepository(session)
        self._outcomes = EnergyOutcomeRepository(session)

    async def _require_machine(self, tenant_id: uuid.UUID, machine_id: uuid.UUID) -> None:
        if await self._machines.get(tenant_id, machine_id) is None:
            raise EnergyOutcomeQueryMachineNotFoundError(str(machine_id))

    async def get(
        self, tenant_id: uuid.UUID, verification_id: uuid.UUID
    ) -> EnergyOutcomeVerification:
        verification = await self._outcomes.get(tenant_id, verification_id)
        if verification is None:
            raise EnergyOutcomeQueryVerificationNotFoundError(str(verification_id))
        return verification

    async def latest(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> EnergyOutcomeVerification | None:
        await self._require_machine(tenant_id, machine_id)
        return await self._outcomes.latest_for_machine(tenant_id, machine_id)

    async def fleet_latest(self, tenant_id: uuid.UUID) -> list[EnergyOutcomeVerification]:
        return await self._outcomes.list_latest_for_tenant(tenant_id)

    async def history(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        *,
        start: datetime | None,
        end: datetime | None,
        limit: int,
    ) -> list[EnergyOutcomeVerification]:
        await self._require_machine(tenant_id, machine_id)
        return await self._outcomes.list_for_machine(
            tenant_id, machine_id, start=start, end=end, limit=limit
        )
