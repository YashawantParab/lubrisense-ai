"""`ConditionAssessment` repository — tenant-scoped, append-only (each `ConditionEngine.
assess()` call inserts a fresh row; history is never overwritten)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import ConditionAssessment


class ConditionAssessmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert(self, assessment: ConditionAssessment) -> ConditionAssessment:
        self.session.add(assessment)
        await self.session.flush()
        # Without a refresh, the enum-typed columns on this in-memory object still hold the
        # plain Python strings assigned at construction, not the `Enum` members SQLAlchemy
        # would hydrate from a real SELECT — `assessment.condition_type.value` raises
        # `AttributeError: 'str' object has no attribute 'value'` until this happens. Found
        # live when `DecisionEngine` immediately consumed a freshly-inserted
        # `ConditionAssessment` in the same request.
        await self.session.refresh(assessment)
        return assessment

    async def get_by_id(
        self, tenant_id: uuid.UUID, assessment_id: uuid.UUID
    ) -> ConditionAssessment | None:
        result = await self.session.execute(
            select(ConditionAssessment).where(
                ConditionAssessment.tenant_id == tenant_id,
                ConditionAssessment.id == assessment_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_latest(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> ConditionAssessment | None:
        result = await self.session.execute(
            select(ConditionAssessment)
            .where(
                ConditionAssessment.tenant_id == tenant_id,
                ConditionAssessment.machine_id == machine_id,
            )
            .order_by(ConditionAssessment.as_of_timestamp.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_recent(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID, *, limit: int = 5
    ) -> list[ConditionAssessment]:
        """Most recent assessments, descending — used by lifecycle classification to
        count consecutive same-`condition_type` rows without an unbounded scan."""
        result = await self.session.execute(
            select(ConditionAssessment)
            .where(
                ConditionAssessment.tenant_id == tenant_id,
                ConditionAssessment.machine_id == machine_id,
            )
            .order_by(ConditionAssessment.as_of_timestamp.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_for_machine(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> list[ConditionAssessment]:
        clauses = [
            ConditionAssessment.tenant_id == tenant_id,
            ConditionAssessment.machine_id == machine_id,
        ]
        if start is not None:
            clauses.append(ConditionAssessment.as_of_timestamp >= start)
        if end is not None:
            clauses.append(ConditionAssessment.as_of_timestamp <= end)
        result = await self.session.execute(
            select(ConditionAssessment)
            .where(*clauses)
            .order_by(ConditionAssessment.as_of_timestamp.desc())
            .limit(min(limit, 1000))
        )
        return list(result.scalars().all())
