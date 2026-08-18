"""Persistence for `BaselineProfile` (Phase 8 brief §16/§17/§27/§30).

"Current" row = whichever row in one `(tenant_id, sensor_id, strategy, context_key)`
lineage is not yet `SUPERSEDED`/`INVALIDATED` — at most one such row should exist at a
time, an invariant the engine maintains by only ever writing through `promote`/
`update_in_place`/`invalidate` below, never a raw insert after the first version. This
mirrors `SensorQualityState`'s single-current-row-per-sensor convention (Phase 7) closely
enough to reuse the same "upsert via the service layer, never bypass it" discipline,
without needing a second partial-unique index beyond `uq_baseline_profile_active`
(non-ACTIVE current states — BUILDING/INSUFFICIENT_DATA/STALE — are transient enough in
practice for one worker process that a DB-level constraint would add ceremony without a
real concurrent-writer risk at this reference implementation's scale).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import BaselineState, BaselineStrategyType
from app.domain.models import BaselineProfile

_TERMINAL_STATES = (BaselineState.SUPERSEDED, BaselineState.INVALIDATED)


class BaselineProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_current(
        self,
        tenant_id: uuid.UUID,
        sensor_id: uuid.UUID,
        strategy: BaselineStrategyType,
        context_key: str,
    ) -> BaselineProfile | None:
        stmt = (
            select(BaselineProfile)
            .where(
                BaselineProfile.tenant_id == tenant_id,
                BaselineProfile.sensor_id == sensor_id,
                BaselineProfile.strategy == strategy,
                BaselineProfile.context_key == context_key,
                BaselineProfile.state.notin_(_TERMINAL_STATES),
            )
            .order_by(BaselineProfile.version.desc())
            .limit(1)
        )
        result: BaselineProfile | None = await self.session.scalar(stmt)
        return result

    async def get_active(
        self,
        tenant_id: uuid.UUID,
        sensor_id: uuid.UUID,
        strategy: BaselineStrategyType,
        context_key: str,
    ) -> BaselineProfile | None:
        stmt = select(BaselineProfile).where(
            BaselineProfile.tenant_id == tenant_id,
            BaselineProfile.sensor_id == sensor_id,
            BaselineProfile.strategy == strategy,
            BaselineProfile.context_key == context_key,
            BaselineProfile.state == BaselineState.ACTIVE,
        )
        result: BaselineProfile | None = await self.session.scalar(stmt)
        return result

    async def list_current_for_sensor(
        self, tenant_id: uuid.UUID, sensor_id: uuid.UUID
    ) -> list[BaselineProfile]:
        stmt = (
            select(BaselineProfile)
            .where(
                BaselineProfile.tenant_id == tenant_id,
                BaselineProfile.sensor_id == sensor_id,
                BaselineProfile.state.notin_(_TERMINAL_STATES),
            )
            .order_by(BaselineProfile.strategy, BaselineProfile.context_key)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_current_for_machine(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> list[BaselineProfile]:
        stmt = (
            select(BaselineProfile)
            .where(
                BaselineProfile.tenant_id == tenant_id,
                BaselineProfile.machine_id == machine_id,
                BaselineProfile.state.notin_(_TERMINAL_STATES),
            )
            .order_by(BaselineProfile.sensor_id, BaselineProfile.strategy)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_current_for_tenant(self, tenant_id: uuid.UUID) -> list[BaselineProfile]:
        stmt = select(BaselineProfile).where(
            BaselineProfile.tenant_id == tenant_id,
            BaselineProfile.state.notin_(_TERMINAL_STATES),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_all_current(self) -> list[BaselineProfile]:
        """Cross-tenant — only for the worker's refresh loop, never exposed via the
        tenant-scoped API (mirrors `SensorQualityStateRepository.list_all_tracked`)."""
        stmt = select(BaselineProfile).where(BaselineProfile.state.notin_(_TERMINAL_STATES))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_versions_for_sensor(
        self, tenant_id: uuid.UUID, sensor_id: uuid.UUID
    ) -> list[BaselineProfile]:
        """Every version ever created for this sensor, including superseded/invalidated
        history (brief §16 — provenance preserved, never deleted)."""
        stmt = (
            select(BaselineProfile)
            .where(BaselineProfile.tenant_id == tenant_id, BaselineProfile.sensor_id == sensor_id)
            .order_by(
                BaselineProfile.strategy, BaselineProfile.context_key, BaselineProfile.version
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_initial(self, **fields: Any) -> BaselineProfile:
        """`version` is 1 for a genuinely new lineage, but max(version)+1 if this lineage
        already has invalidated/superseded history (e.g. a fresh generation started right
        after a firmware-change invalidation, brief §17/§18) — `uq_baseline_profile_version`
        would otherwise collide with the still-present historical row at version 1."""
        next_version = await self._next_version(
            fields["tenant_id"], fields["sensor_id"], fields["strategy"], fields["context_key"]
        )
        profile = BaselineProfile(version=next_version, **fields)
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def _next_version(
        self,
        tenant_id: uuid.UUID,
        sensor_id: uuid.UUID,
        strategy: BaselineStrategyType,
        context_key: str,
    ) -> int:
        stmt = select(func.max(BaselineProfile.version)).where(
            BaselineProfile.tenant_id == tenant_id,
            BaselineProfile.sensor_id == sensor_id,
            BaselineProfile.strategy == strategy,
            BaselineProfile.context_key == context_key,
        )
        current_max = await self.session.scalar(stmt)
        return (current_max or 0) + 1

    async def update_in_place(self, profile_id: uuid.UUID, **fields: Any) -> None:
        """No version bump, no state transition beyond what's passed in `fields` — used
        for candidate-tracking updates and no-op refresh cycles (idempotency, brief §30)."""
        await self.session.execute(
            update(BaselineProfile).where(BaselineProfile.id == profile_id).values(**fields)
        )

    async def promote(
        self,
        current: BaselineProfile,
        *,
        statistics: dict[str, Any],
        sample_count: int,
        window_start: datetime | None,
        window_end: datetime | None,
        now: datetime,
    ) -> BaselineProfile:
        """Ends `current`'s lineage membership (SUPERSEDED if it was ACTIVE, otherwise the
        row simply stops being "current" — see module docstring) and inserts a new ACTIVE
        version. Called only after the stability gate has confirmed the candidate (brief
        §41's "activation requires stability window")."""
        await self.session.execute(
            update(BaselineProfile)
            .where(BaselineProfile.id == current.id)
            .values(state=BaselineState.SUPERSEDED, superseded_at=now)
        )
        new_version = BaselineProfile(
            tenant_id=current.tenant_id,
            sensor_id=current.sensor_id,
            machine_id=current.machine_id,
            measurement_type=current.measurement_type,
            strategy=current.strategy,
            metric_kind=current.metric_kind,
            context_key=current.context_key,
            context=current.context,
            version=current.version + 1,
            state=BaselineState.ACTIVE,
            statistics=statistics,
            sample_count=sample_count,
            min_sample_required=current.min_sample_required,
            window_start=window_start,
            window_end=window_end,
            window_seconds=current.window_seconds,
            candidate_stable_cycles=0,
            config_version=current.config_version,
            quality_policy_version=current.quality_policy_version,
            activated_at=now,
            last_evaluated_at=now,
            refresh_interval_seconds=current.refresh_interval_seconds,
            stale_after_seconds=current.stale_after_seconds,
            firmware_version=current.firmware_version,
            controller_version=current.controller_version,
        )
        self.session.add(new_version)
        await self.session.flush()
        return new_version

    async def invalidate(self, profile_id: uuid.UUID, *, reason: str, now: datetime) -> None:
        await self.session.execute(
            update(BaselineProfile)
            .where(BaselineProfile.id == profile_id)
            .values(state=BaselineState.INVALIDATED, invalidated_at=now, invalidation_reason=reason)
        )

    async def mark_stale(self, profile_id: uuid.UUID) -> None:
        await self.session.execute(
            update(BaselineProfile)
            .where(BaselineProfile.id == profile_id)
            .values(state=BaselineState.STALE)
        )

    async def count_by_state(self, tenant_id: uuid.UUID) -> dict[str, int]:
        current = await self.list_current_for_tenant(tenant_id)
        counts: dict[str, int] = {}
        for profile in current:
            counts[profile.state.value] = counts.get(profile.state.value, 0) + 1
        return counts
