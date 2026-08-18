"""Idempotent feature-vector persistence and tenant-scoped reads."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import FeatureVector
from app.features.domain.models import FeatureComputationResult


class FeatureRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def materialize(
        self, result: FeatureComputationResult, policy_version: str
    ) -> tuple[FeatureVector, bool]:
        values = {
            "id": result.feature_vector_id,
            "tenant_id": result.tenant_id,
            "machine_id": result.machine_id,
            "component_id": result.component_id,
            "entity_key": str(result.component_id or result.machine_id),
            "feature_set": result.feature_set,
            "feature_set_version": result.feature_set_version,
            "as_of_timestamp": result.as_of_timestamp,
            "feature_values": result.feature_values,
            "missing_features": list(result.missing_features),
            "quality_summary": result.quality_summary,
            "source_window": result.source_window,
            "baseline_versions": result.baseline_versions,
            "rule_versions": result.rule_versions,
            "feature_definition_versions": result.feature_definition_versions,
            "feature_policy_version": policy_version,
        }
        statement = (
            pg_insert(FeatureVector.__table__)  # type: ignore[arg-type]
            .values(**values)
            .on_conflict_do_nothing(constraint="uq_feature_vector_logical")
            .returning(FeatureVector.id)
        )
        inserted_id = await self.session.scalar(statement)
        row = await self.get_by_id(result.tenant_id, result.feature_vector_id)
        if row is None:
            raise RuntimeError("Feature vector insert/fetch invariant failed")
        return row, inserted_id is not None

    async def get_by_id(self, tenant_id: uuid.UUID, vector_id: uuid.UUID) -> FeatureVector | None:
        result: FeatureVector | None = await self.session.scalar(
            select(FeatureVector).where(
                FeatureVector.tenant_id == tenant_id, FeatureVector.id == vector_id
            )
        )
        return result

    async def get_latest(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID, feature_set: str | None = None
    ) -> FeatureVector | None:
        clauses = [FeatureVector.tenant_id == tenant_id, FeatureVector.machine_id == machine_id]
        if feature_set is not None:
            clauses.append(FeatureVector.feature_set == feature_set)
        result: FeatureVector | None = await self.session.scalar(
            select(FeatureVector)
            .where(*clauses)
            .order_by(FeatureVector.as_of_timestamp.desc(), FeatureVector.created_at.desc())
            .limit(1)
        )
        return result

    async def list_for_machine(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        *,
        feature_set: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> list[FeatureVector]:
        clauses = [FeatureVector.tenant_id == tenant_id, FeatureVector.machine_id == machine_id]
        if feature_set is not None:
            clauses.append(FeatureVector.feature_set == feature_set)
        if start is not None:
            clauses.append(FeatureVector.as_of_timestamp >= start)
        if end is not None:
            clauses.append(FeatureVector.as_of_timestamp <= end)
        rows = await self.session.execute(
            select(FeatureVector)
            .where(*clauses)
            .order_by(FeatureVector.as_of_timestamp.desc())
            .limit(min(limit, 1000))
        )
        return list(rows.scalars().all())
