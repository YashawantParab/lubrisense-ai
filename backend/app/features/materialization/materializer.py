"""Hybrid storage boundary: compute through `FeatureEngine`, persist selected vectors."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import FeatureVector
from app.features.config.policy import FeaturePolicy
from app.features.repositories.feature_repository import FeatureRepository
from app.features.services.feature_engine import FeatureEngine


@dataclass(frozen=True)
class MaterializationResult:
    vector: FeatureVector
    inserted: bool
    telemetry_rows_scanned: int
    features_generated: int
    features_missing: int


class FeatureMaterializer:
    def __init__(self, session: AsyncSession, policy: FeaturePolicy) -> None:
        self._policy = policy
        self._engine = FeatureEngine(session, policy)
        self._repository = FeatureRepository(session)

    async def materialize(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        feature_set: str,
        as_of: datetime,
    ) -> MaterializationResult:
        computed = await self._engine.compute(tenant_id, machine_id, feature_set, as_of)
        vector, inserted = await self._repository.materialize(computed, self._policy.policy_version)
        return MaterializationResult(
            vector=vector,
            inserted=inserted,
            telemetry_rows_scanned=int(computed.metrics["telemetry_rows_scanned"]),
            features_generated=int(computed.metrics["features_generated"]),
            features_missing=int(computed.metrics["features_missing"]),
        )

    async def materialize_latest(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID, feature_set: str
    ) -> MaterializationResult:
        computed = await self._engine.compute_latest(tenant_id, machine_id, feature_set)
        vector, inserted = await self._repository.materialize(computed, self._policy.policy_version)
        return MaterializationResult(
            vector=vector,
            inserted=inserted,
            telemetry_rows_scanned=int(computed.metrics["telemetry_rows_scanned"]),
            features_generated=int(computed.metrics["features_generated"]),
            features_missing=int(computed.metrics["features_missing"]),
        )
