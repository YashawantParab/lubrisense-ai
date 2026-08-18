"""The baseline fallback hierarchy (Phase 8 brief §22): exact context -> operating-state
-only -> sensor-level (no context) -> engineering reference. Never silently returns an
unrelated context — each rung is a real, explicit lookup, and the caller always learns
which rung actually answered (`BaselineSourceKind`), never just a bare statistics object.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.baselines.config.policy import BaselinePolicy
from app.baselines.domain.context import BaselineContext, context_key
from app.baselines.repositories.baseline_profile_repository import BaselineProfileRepository
from app.domain.enums import BaselineSourceKind, BaselineStrategyType
from app.domain.models import BaselineProfile, Sensor


@dataclass(frozen=True)
class ResolvedBaseline:
    profile: BaselineProfile | None
    source: BaselineSourceKind


async def resolve_baseline(
    session: AsyncSession,
    policy: BaselinePolicy,
    tenant_id: uuid.UUID,
    sensor: Sensor,
    requested_context: BaselineContext,
) -> ResolvedBaseline:
    repo = BaselineProfileRepository(session)
    measurement_type = sensor.sensor_type.value

    if policy.is_contextual(measurement_type):
        exact = await repo.get_active(
            tenant_id,
            sensor.id,
            BaselineStrategyType.CONTEXTUAL_ASSET_BASELINE,
            context_key(requested_context),
        )
        if exact is not None:
            return ResolvedBaseline(exact, BaselineSourceKind.EXACT_CONTEXT)

        if requested_context.cycle_phase is not None and policy.uses_cycle_phase(measurement_type):
            coarse_key = context_key(
                BaselineContext(operating_state=requested_context.operating_state)
            )
            coarse = await repo.get_active(
                tenant_id, sensor.id, BaselineStrategyType.CONTEXTUAL_ASSET_BASELINE, coarse_key
            )
            if coarse is not None:
                return ResolvedBaseline(coarse, BaselineSourceKind.OPERATING_STATE)

    sensor_level = await repo.get_active(
        tenant_id, sensor.id, BaselineStrategyType.ROLLING_ASSET_BASELINE, ""
    )
    if sensor_level is not None:
        return ResolvedBaseline(sensor_level, BaselineSourceKind.SENSOR_LEVEL)

    reference = await repo.get_active(
        tenant_id, sensor.id, BaselineStrategyType.STATIC_ENGINEERING_REFERENCE, ""
    )
    if reference is not None:
        return ResolvedBaseline(reference, BaselineSourceKind.ENGINEERING_REFERENCE)

    return ResolvedBaseline(None, BaselineSourceKind.NONE)
