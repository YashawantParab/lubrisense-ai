"""Point-in-time feature orchestration shared by every serving mode."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.config.policy import FeaturePolicy
from app.features.definitions.sets import FEATURE_SETS
from app.features.domain.models import FeatureComputationResult
from app.features.repositories.source_repository import FeatureSourceRepository
from app.features.services.computation import compute_feature_values, definition_versions

FEATURE_VECTOR_NAMESPACE = uuid.UUID("a9e3d144-3c32-5a8f-91b4-1bb20c38f0b7")


class FeatureMachineNotFoundError(LookupError):
    pass


class FeatureEngine:
    def __init__(self, session: AsyncSession, policy: FeaturePolicy) -> None:
        self.session = session
        self.policy = policy
        self._source_repository = FeatureSourceRepository(session)

    async def compute(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        feature_set: str,
        as_of: datetime,
    ) -> FeatureComputationResult:
        if feature_set not in FEATURE_SETS:
            raise ValueError(f"Unknown feature set: {feature_set}")
        if as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        as_of = as_of.astimezone(UTC)
        start = as_of - timedelta(seconds=self.policy.maximum_lookback_seconds)
        context = await self._source_repository.load_context(
            tenant_id,
            machine_id,
            start=start,
            as_of=as_of,
            maximum_rows=self.policy.maximum_rows_per_vector,
        )
        if context is None:
            raise FeatureMachineNotFoundError(str(machine_id))

        values, missing, quality, baselines, rules, metrics = compute_feature_values(
            context, feature_set, self.policy
        )
        set_definition = FEATURE_SETS[feature_set]
        logical_key = (
            f"{tenant_id}|{machine_id}|MACHINE|{feature_set}|"
            f"{set_definition.version}|{as_of.isoformat()}"
        )
        observed_start = min((point.source_timestamp for point in context.points), default=None)
        observed_end = max((point.source_timestamp for point in context.points), default=None)
        source_window: dict[str, object] = {
            "requested_start": start.isoformat(),
            "requested_end": as_of.isoformat(),
            "observed_start": observed_start.isoformat() if observed_start else None,
            "observed_end": observed_end.isoformat() if observed_end else None,
            "event_time_field": "source_timestamp",
            "telemetry_rows_scanned": context.telemetry_rows_scanned,
        }
        return FeatureComputationResult(
            feature_vector_id=uuid.uuid5(FEATURE_VECTOR_NAMESPACE, logical_key),
            feature_set=feature_set,
            feature_set_version=set_definition.version,
            tenant_id=tenant_id,
            machine_id=machine_id,
            component_id=None,
            as_of_timestamp=as_of,
            feature_values=values,
            missing_features=missing,
            quality_summary=quality,
            source_window=source_window,
            baseline_versions=baselines,
            rule_versions=rules,
            feature_definition_versions=definition_versions(feature_set),
            created_at=datetime.now(UTC),
            metrics=metrics,
        )

    async def compute_latest(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID, feature_set: str
    ) -> FeatureComputationResult:
        as_of = await self._source_repository.latest_source_timestamp(tenant_id, machine_id)
        return await self.compute(tenant_id, machine_id, feature_set, as_of or datetime.now(UTC))
