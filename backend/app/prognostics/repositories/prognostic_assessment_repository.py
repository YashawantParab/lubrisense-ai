"""`PrognosticAssessment` repository — tenant-scoped, append-only."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import PrognosticAssessment


class PrognosticAssessmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert(self, assessment: PrognosticAssessment) -> PrognosticAssessment:
        self.session.add(assessment)
        await self.session.flush()
        # See the identical comment in
        # `app.condition_intelligence.repositories.condition_assessment_repository` — a
        # freshly-inserted, unrefreshed ORM object's enum-typed columns are still plain
        # strings until re-hydrated from the database.
        await self.session.refresh(assessment)
        return assessment

    async def get_latest(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID, state_type: str, horizon: str
    ) -> PrognosticAssessment | None:
        result = await self.session.execute(
            select(PrognosticAssessment)
            .where(
                PrognosticAssessment.tenant_id == tenant_id,
                PrognosticAssessment.machine_id == machine_id,
                PrognosticAssessment.state_type == state_type,
                PrognosticAssessment.horizon == horizon,
            )
            .order_by(PrognosticAssessment.as_of_timestamp.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_latest_for_machine(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> list[PrognosticAssessment]:
        """The most recent row per `(state_type, horizon)` — used by the `/latest` API and
        the combined `/intelligence` view."""
        result = await self.session.execute(
            select(PrognosticAssessment)
            .where(
                PrognosticAssessment.tenant_id == tenant_id,
                PrognosticAssessment.machine_id == machine_id,
            )
            .order_by(PrognosticAssessment.as_of_timestamp.desc())
            .limit(200)
        )
        rows = result.scalars().all()
        latest: dict[tuple[str, str], PrognosticAssessment] = {}
        for row in rows:
            key = (row.state_type.value, row.horizon.value)
            if key not in latest:
                latest[key] = row
        return list(latest.values())

    async def list_for_machine(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        *,
        state_type: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> list[PrognosticAssessment]:
        clauses = [
            PrognosticAssessment.tenant_id == tenant_id,
            PrognosticAssessment.machine_id == machine_id,
        ]
        if state_type is not None:
            clauses.append(PrognosticAssessment.state_type == state_type)
        if start is not None:
            clauses.append(PrognosticAssessment.as_of_timestamp >= start)
        if end is not None:
            clauses.append(PrognosticAssessment.as_of_timestamp <= end)
        result = await self.session.execute(
            select(PrognosticAssessment)
            .where(*clauses)
            .order_by(PrognosticAssessment.as_of_timestamp.desc())
            .limit(min(limit, 1000))
        )
        return list(result.scalars().all())
