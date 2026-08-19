"""`Incident` repository — tenant-scoped."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import IncidentState
from app.domain.models import Incident

_TERMINAL_STATES = (IncidentState.RESOLVED, IncidentState.CLOSED)


class IncidentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert(self, incident: Incident) -> Incident:
        self.session.add(incident)
        await self.session.flush()
        # Same enum-hydration reason as `ConditionAssessmentRepository.insert` (ADR-122):
        # a freshly-added, unrefreshed ORM object's enum-typed columns are still plain
        # strings until re-hydrated from the database.
        await self.session.refresh(incident)
        return incident

    async def save(self, incident: Incident) -> Incident:
        """Persist in-place mutations to an already-tracked `Incident` (evidence-append,
        lifecycle transitions). A plain `flush()` + `refresh()` is sufficient — unlike
        `DecisionAssessment`, `Incident` genuinely mutates in place; it is not
        append-only (Phase 16 brief §16.10: "update... append timeline event... do not
        create a duplicate incident")."""
        await self.session.flush()
        await self.session.refresh(incident)
        return incident

    async def get(self, tenant_id: uuid.UUID, incident_id: uuid.UUID) -> Incident | None:
        result = await self.session.execute(
            select(Incident).where(Incident.tenant_id == tenant_id, Incident.id == incident_id)
        )
        return result.scalar_one_or_none()

    async def get_open_by_correlation_key(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID, correlation_key: str
    ) -> Incident | None:
        result = await self.session.execute(
            select(Incident).where(
                Incident.tenant_id == tenant_id,
                Incident.machine_id == machine_id,
                Incident.correlation_key == correlation_key,
                Incident.state.not_in(_TERMINAL_STATES),
            )
        )
        return result.scalar_one_or_none()

    async def list_open_for_machine(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> list[Incident]:
        result = await self.session.execute(
            select(Incident).where(
                Incident.tenant_id == tenant_id,
                Incident.machine_id == machine_id,
                Incident.state.not_in(_TERMINAL_STATES),
            )
        )
        return list(result.scalars().all())

    async def list_for_tenant(
        self,
        tenant_id: uuid.UUID,
        *,
        machine_id: uuid.UUID | None = None,
        state: IncidentState | None = None,
        limit: int = 200,
    ) -> list[Incident]:
        clauses = [Incident.tenant_id == tenant_id]
        if machine_id is not None:
            clauses.append(Incident.machine_id == machine_id)
        if state is not None:
            clauses.append(Incident.state == state)
        result = await self.session.execute(
            select(Incident)
            .where(*clauses)
            .order_by(Incident.created_at.desc())
            .limit(min(limit, 1000))
        )
        return list(result.scalars().all())
