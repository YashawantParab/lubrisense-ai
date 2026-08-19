"""Tenant-scoped persistence for `StateEstimate` (Phase 12 brief §17), mirroring
`app.features.repositories.feature_repository.FeatureRepository`'s idempotent-insert
pattern: `ON CONFLICT DO NOTHING` on the logical unique constraint, then a definite
fetch-back, so a repeated historical-replay run over the same window never duplicates rows
and always returns the one row that logically exists either way.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import StateEstimate
from app.state_estimation.domain.models import StateEstimateResult


class StateEstimateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def persist(self, result: StateEstimateResult) -> tuple[StateEstimate, bool]:
        values = {
            "id": uuid.uuid4(),
            "tenant_id": result.tenant_id,
            "machine_id": result.machine_id,
            "component_id": result.component_id,
            "state_type": result.state_type,
            "as_of_timestamp": result.as_of_timestamp,
            "state_value": result.state_value,
            "state_rate": result.state_rate,
            "trend": result.trend,
            "uncertainty": result.uncertainty,
            "covariance_summary": result.covariance_summary,
            "estimator_id": result.estimator_id,
            "estimator_version": result.estimator_version,
            "config_version": result.config_version,
            "feature_set": result.feature_set,
            "feature_set_version": result.feature_set_version,
            "feature_vector_id": result.feature_vector_id,
            "dt_seconds": result.dt_seconds,
            "prediction_only": result.prediction_only,
            "observations_used": list(result.observations_used),
            "observations_missing": list(result.observations_missing),
            "quality_summary": result.quality_summary,
        }
        statement = (
            pg_insert(StateEstimate)
            .values(**values)
            .on_conflict_do_nothing(constraint="uq_state_estimate_logical")
            .returning(StateEstimate.id)
        )
        inserted_id = await self.session.scalar(statement)
        row = await self.get_logical(
            result.tenant_id,
            result.machine_id,
            result.state_type,
            result.as_of_timestamp,
            result.estimator_version,
        )
        if row is None:
            raise RuntimeError("State estimate insert/fetch invariant failed")
        return row, inserted_id is not None

    async def get_logical(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        state_type: str,
        as_of_timestamp: datetime,
        estimator_version: str,
    ) -> StateEstimate | None:
        result: StateEstimate | None = await self.session.scalar(
            select(StateEstimate).where(
                StateEstimate.tenant_id == tenant_id,
                StateEstimate.machine_id == machine_id,
                StateEstimate.state_type == state_type,
                StateEstimate.as_of_timestamp == as_of_timestamp,
                StateEstimate.estimator_version == estimator_version,
            )
        )
        return result

    async def get_latest(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        state_type: str,
        estimator_version: str,
    ) -> StateEstimate | None:
        """The most recent prior estimate a filter run continues from — ordered by
        `as_of_timestamp`, never `created_at`, so an out-of-order historical replay call
        still continues from the logically-latest tick, not the most-recently-inserted
        row."""
        result: StateEstimate | None = await self.session.scalar(
            select(StateEstimate)
            .where(
                StateEstimate.tenant_id == tenant_id,
                StateEstimate.machine_id == machine_id,
                StateEstimate.state_type == state_type,
                StateEstimate.estimator_version == estimator_version,
            )
            .order_by(StateEstimate.as_of_timestamp.desc())
            .limit(1)
        )
        return result

    async def list_for_machine(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        *,
        state_type: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> list[StateEstimate]:
        clauses = [StateEstimate.tenant_id == tenant_id, StateEstimate.machine_id == machine_id]
        if state_type is not None:
            clauses.append(StateEstimate.state_type == state_type)
        if start is not None:
            clauses.append(StateEstimate.as_of_timestamp >= start)
        if end is not None:
            clauses.append(StateEstimate.as_of_timestamp <= end)
        rows = await self.session.execute(
            select(StateEstimate)
            .where(*clauses)
            .order_by(StateEstimate.as_of_timestamp.desc())
            .limit(min(limit, 1000))
        )
        return list(rows.scalars().all())
