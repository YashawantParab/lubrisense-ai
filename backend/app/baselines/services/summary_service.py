"""Baseline readiness rollups (Phase 8 brief §26/§43) — this is baseline *readiness*
("has enough been learned to be useful"), explicitly not machine/asset health.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.baselines.repositories.baseline_profile_repository import BaselineProfileRepository
from app.domain.enums import BaselineState, BaselineStrategyType
from app.domain.models import BaselineProfile

_LEARNED_STRATEGIES = (
    BaselineStrategyType.ROLLING_ASSET_BASELINE,
    BaselineStrategyType.CONTEXTUAL_ASSET_BASELINE,
)


@dataclass(frozen=True)
class Readiness:
    label: str  # "READY" | "PARTIAL" | "NOT_READY"
    active_count: int
    building_count: int
    insufficient_data_count: int
    stale_count: int
    invalidated_count: int


def _classify(profiles: list[BaselineProfile]) -> Readiness:
    learned = [p for p in profiles if p.strategy in _LEARNED_STRATEGIES]
    active = sum(1 for p in learned if p.state == BaselineState.ACTIVE)
    building = sum(1 for p in learned if p.state == BaselineState.BUILDING)
    insufficient = sum(1 for p in learned if p.state == BaselineState.INSUFFICIENT_DATA)
    stale = sum(1 for p in learned if p.state == BaselineState.STALE)
    invalidated = sum(1 for p in learned if p.state == BaselineState.INVALIDATED)

    if not learned:
        label = "NOT_READY"
    elif active > 0 and building == 0 and insufficient == 0:
        label = "READY"
    elif active > 0:
        label = "PARTIAL"
    else:
        label = "NOT_READY"

    return Readiness(
        label=label,
        active_count=active,
        building_count=building,
        insufficient_data_count=insufficient,
        stale_count=stale,
        invalidated_count=invalidated,
    )


class BaselineSummaryService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = BaselineProfileRepository(session)

    async def sensor_readiness(self, tenant_id: uuid.UUID, sensor_id: uuid.UUID) -> Readiness:
        profiles = await self._repo.list_current_for_sensor(tenant_id, sensor_id)
        return _classify(profiles)

    async def machine_readiness(self, tenant_id: uuid.UUID, machine_id: uuid.UUID) -> Readiness:
        profiles = await self._repo.list_current_for_machine(tenant_id, machine_id)
        return _classify(profiles)

    async def tenant_summary(self, tenant_id: uuid.UUID) -> dict[str, int]:
        return await self._repo.count_by_state(tenant_id)
