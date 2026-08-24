"""`MaintenanceCase` repository — tenant-scoped."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import MaintenanceState
from app.domain.models import MaintenanceCase

_TERMINAL_STATES = (MaintenanceState.COMPLETED, MaintenanceState.CANCELLED)


class MaintenanceCaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert(self, case: MaintenanceCase) -> MaintenanceCase:
        self.session.add(case)
        await self.session.flush()
        await self.session.refresh(case)
        return case

    async def save(self, case: MaintenanceCase) -> MaintenanceCase:
        await self.session.flush()
        await self.session.refresh(case)
        return case

    async def get(self, tenant_id: uuid.UUID, case_id: uuid.UUID) -> MaintenanceCase | None:
        result = await self.session.execute(
            select(MaintenanceCase).where(
                MaintenanceCase.tenant_id == tenant_id, MaintenanceCase.id == case_id
            )
        )
        return result.scalar_one_or_none()

    async def get_active_for_incident(
        self, tenant_id: uuid.UUID, incident_id: uuid.UUID
    ) -> MaintenanceCase | None:
        result = await self.session.execute(
            select(MaintenanceCase).where(
                MaintenanceCase.tenant_id == tenant_id,
                MaintenanceCase.incident_id == incident_id,
                MaintenanceCase.state.not_in(_TERMINAL_STATES),
            )
        )
        return result.scalar_one_or_none()

    async def list_completed_for_machine(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID, *, limit: int = 50
    ) -> list[MaintenanceCase]:
        """Most-recent-first `COMPLETED` cases for one machine (Lubrication Efficiency
        Intelligence, Pass 3 — docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md §9, ADR-176).
        `EnergyOutcomeService` anchors its window selection on the most recent one; older
        completed cases remain available here for a future multi-intervention history
        view, not consumed by this pass."""
        result = await self.session.execute(
            select(MaintenanceCase)
            .where(
                MaintenanceCase.tenant_id == tenant_id,
                MaintenanceCase.machine_id == machine_id,
                MaintenanceCase.state == MaintenanceState.COMPLETED,
            )
            .order_by(MaintenanceCase.completed_at.desc())
            .limit(min(limit, 200))
        )
        return list(result.scalars().all())

    async def list_for_tenant(
        self,
        tenant_id: uuid.UUID,
        *,
        state: MaintenanceState | None = None,
        limit: int = 200,
    ) -> list[MaintenanceCase]:
        clauses = [MaintenanceCase.tenant_id == tenant_id]
        if state is not None:
            clauses.append(MaintenanceCase.state == state)
        result = await self.session.execute(
            select(MaintenanceCase)
            .where(*clauses)
            .order_by(MaintenanceCase.created_at.desc())
            .limit(min(limit, 1000))
        )
        return list(result.scalars().all())
