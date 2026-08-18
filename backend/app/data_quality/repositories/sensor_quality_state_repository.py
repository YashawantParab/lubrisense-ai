"""Upsert-by-PK persistence for `SensorQualityState` — the always-current, cheap-to-query
summary row per sensor (Phase 7 brief §29; plan decision #4)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_quality.domain.context import SensorContext
from app.domain.enums import ClockStatus, Eligibility, QualityState, StalenessStatus
from app.domain.models import SensorQualityState


class SensorQualityStateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, tenant_id: uuid.UUID, sensor_id: uuid.UUID) -> SensorQualityState | None:
        stmt = select(SensorQualityState).where(
            SensorQualityState.tenant_id == tenant_id, SensorQualityState.sensor_id == sensor_id
        )
        result: SensorQualityState | None = await self.session.scalar(stmt)
        return result

    async def get_context(self, tenant_id: uuid.UUID, sensor_id: uuid.UUID) -> SensorContext:
        """The ORM-to-pure-dataclass conversion boundary rules rely on (Phase 7 brief
        §60) — never hand a live `SensorQualityState` row to a rule function."""
        row = await self.get(tenant_id, sensor_id)
        if row is None:
            return SensorContext.initial(tenant_id, sensor_id)
        return SensorContext(
            tenant_id=tenant_id,
            sensor_id=sensor_id,
            machine_id=row.machine_id,
            quality_state=row.quality_state,
            eligibility=row.eligibility,
            last_good_reading_at=row.last_good_reading_at,
            last_good_reading_value=row.last_good_reading_value,
            last_observed_at=row.last_observed_at,
            last_observed_value=row.last_observed_value,
            last_observed_quality=row.last_observed_quality,
            last_observed_operating_state=row.last_observed_operating_state,
            last_source_timestamp_seen=row.last_source_timestamp_seen,
            expected_next_sequence=row.expected_next_sequence,
            staleness_status=row.staleness_status,
            clock_status=row.clock_status,
            active_issue_count=row.active_issue_count,
            firmware_version=row.firmware_version,
            controller_version=row.controller_version,
        )

    async def list_for_machine(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> list[SensorQualityState]:
        stmt = select(SensorQualityState).where(
            SensorQualityState.tenant_id == tenant_id, SensorQualityState.machine_id == machine_id
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_tenant(
        self, tenant_id: uuid.UUID, *, limit: int = 500
    ) -> list[SensorQualityState]:
        stmt = (
            select(SensorQualityState)
            .where(SensorQualityState.tenant_id == tenant_id)
            .order_by(SensorQualityState.updated_at.desc())
            .limit(min(limit, 2000))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_all_tracked(self) -> list[SensorQualityState]:
        """Cross-tenant, unlike every other method here — only for the worker's periodic
        window-evaluation loop (`app/data_quality/worker.py`), never exposed through the
        tenant-scoped API."""
        result = await self.session.execute(select(SensorQualityState))
        return list(result.scalars().all())

    async def count_by_state(
        self, tenant_id: uuid.UUID, *, machine_id: uuid.UUID | None = None
    ) -> dict[str, int]:
        clauses = [SensorQualityState.tenant_id == tenant_id]
        if machine_id is not None:
            clauses.append(SensorQualityState.machine_id == machine_id)
        stmt = (
            select(SensorQualityState.quality_state, func.count())
            .where(*clauses)
            .group_by(SensorQualityState.quality_state)
        )
        result = await self.session.execute(stmt)
        return {state.value: count for state, count in result.all()}

    async def upsert(self, tenant_id: uuid.UUID, sensor_id: uuid.UUID, **fields: Any) -> None:
        """Merge-patch: only the keys passed in `fields` are set on conflict, so a caller
        that only knows the event-level fields (`QualityEngine`) never clobbers the
        window-level fields (`WindowEvaluator`) it didn't touch, and vice versa. Defaults
        fill the remaining NOT NULL columns for the INSERT branch only (a sensor seen for
        the first time) — they never appear in the UPDATE SET clause."""
        insert_values = {
            **self._default_insert_fields(),
            "tenant_id": tenant_id,
            "sensor_id": sensor_id,
            **fields,
        }
        stmt = pg_insert(SensorQualityState.__table__).values(**insert_values)  # type: ignore[arg-type]
        stmt = stmt.on_conflict_do_update(
            constraint="pk_sensor_quality_state",
            set_={key: stmt.excluded[key] for key in fields},
        )
        await self.session.execute(stmt)

    @staticmethod
    def _default_insert_fields() -> dict[str, Any]:
        return {
            "quality_state": QualityState.TRUSTED,
            "eligibility": Eligibility.ELIGIBLE,
            "staleness_status": StalenessStatus.UNKNOWN,
            "clock_status": ClockStatus.UNKNOWN,
            "active_issue_count": 0,
        }
