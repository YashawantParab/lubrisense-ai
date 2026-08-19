"""`DecisionAssessment` repository — tenant-scoped. Unlike every other Phase 13-15 table,
this one performs one real UPDATE: when a new decision is inserted for a machine, the
previously-ACTIVE row (if any) transitions to SUPERSEDED in place — Phase 14 brief §14.12
is explicit that a prior decision must never be silently overwritten (deleted or replaced
with no trace), so SUPERSEDED is a lifecycle transition on the same row, not a delete."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import DecisionLifecycle
from app.domain.models import DecisionAssessment


class DecisionAssessmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert_and_supersede_prior(
        self, assessment: DecisionAssessment
    ) -> DecisionAssessment:
        await self.session.execute(
            update(DecisionAssessment)
            .where(
                DecisionAssessment.tenant_id == assessment.tenant_id,
                DecisionAssessment.machine_id == assessment.machine_id,
                DecisionAssessment.lifecycle_state == DecisionLifecycle.ACTIVE,
            )
            .values(lifecycle_state=DecisionLifecycle.SUPERSEDED)
        )
        self.session.add(assessment)
        await self.session.flush()
        # See the identical comment in
        # `app.condition_intelligence.repositories.condition_assessment_repository` — a
        # freshly-inserted, unrefreshed ORM object's enum-typed columns are still plain
        # strings until re-hydrated from the database.
        await self.session.refresh(assessment)
        return assessment

    async def get_by_id(
        self, tenant_id: uuid.UUID, assessment_id: uuid.UUID
    ) -> DecisionAssessment | None:
        result = await self.session.execute(
            select(DecisionAssessment).where(
                DecisionAssessment.tenant_id == tenant_id,
                DecisionAssessment.id == assessment_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_latest(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> DecisionAssessment | None:
        result = await self.session.execute(
            select(DecisionAssessment)
            .where(
                DecisionAssessment.tenant_id == tenant_id,
                DecisionAssessment.machine_id == machine_id,
            )
            .order_by(DecisionAssessment.as_of_timestamp.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_for_machine(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> list[DecisionAssessment]:
        clauses = [
            DecisionAssessment.tenant_id == tenant_id,
            DecisionAssessment.machine_id == machine_id,
        ]
        if start is not None:
            clauses.append(DecisionAssessment.as_of_timestamp >= start)
        if end is not None:
            clauses.append(DecisionAssessment.as_of_timestamp <= end)
        result = await self.session.execute(
            select(DecisionAssessment)
            .where(*clauses)
            .order_by(DecisionAssessment.as_of_timestamp.desc())
            .limit(min(limit, 1000))
        )
        return list(result.scalars().all())
