"""Ties `app.baselines.services.fallback` together with
`app.baselines.domain.deviation` — resolves a baseline through the fallback hierarchy for
one sensor/context, then classifies how far a given value sits from it (Phase 8 brief §23).
Backs `GET /api/v1/baselines/sensors/{sensor_id}/current`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.baselines.config.policy import BaselinePolicy
from app.baselines.domain.context import BaselineContext
from app.baselines.domain.deviation import DeviationResult, compute_deviation, not_enough_data
from app.baselines.domain.statistics import RobustStatistics
from app.baselines.services.fallback import ResolvedBaseline, resolve_baseline
from app.domain.enums import BaselineMetricKind
from app.domain.models import Sensor


@dataclass(frozen=True)
class DeviationLookup:
    resolved: ResolvedBaseline
    deviation: DeviationResult | None
    """`None` when no `value` was supplied to `evaluate` — the caller only wanted the
    resolved baseline itself, not a distance."""


async def evaluate(
    session: AsyncSession,
    policy: BaselinePolicy,
    tenant_id: uuid.UUID,
    sensor: Sensor,
    requested_context: BaselineContext,
    value: float | None,
) -> DeviationLookup:
    resolved = await resolve_baseline(session, policy, tenant_id, sensor, requested_context)
    if value is None:
        return DeviationLookup(resolved, None)
    if resolved.profile is None or resolved.profile.statistics is None:
        return DeviationLookup(resolved, not_enough_data())
    if resolved.profile.metric_kind != BaselineMetricKind.STANDARD:
        # Deviation against a trend/cycle-shaped baseline isn't the same "single-reading
        # distance" question — not computed here (brief §23 scopes this to a value vs. a
        # numeric distribution).
        return DeviationLookup(resolved, not_enough_data())
    stats = RobustStatistics(**resolved.profile.statistics)
    deviation = compute_deviation(
        value,
        stats,
        mild_multiplier=policy.deviation.mild_multiplier,
        strong_multiplier=policy.deviation.strong_multiplier,
    )
    return DeviationLookup(resolved, deviation)
