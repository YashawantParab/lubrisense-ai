"""Telemetry persistence and time-range query repository (Phase 6 brief §16/§28/§29).

Not a `TenantScopedRepository[T]` subclass: that generic assumes a single-`id` primary key
and `created_at`-ordered listing, neither of which fits a hypertable keyed on
`(event_id, source_timestamp)` and queried by time range. `batch_insert_idempotent` is the
one method the consumer actually needs at throughput — everything else supports the
read-only query API (app/api/v1/telemetry.py).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import SensorType
from app.domain.models import Telemetry

DEFAULT_QUERY_LIMIT = 200
MAX_QUERY_LIMIT = 2000

# PostgreSQL's wire protocol caps a single statement at 65535 bind parameters, and asyncpg
# enforces that same limit. A batch this size keeps every chunk's parameter count
# (batch rows * columns per row) comfortably under that ceiling — with headroom for the
# widest existing telemetry envelope (~33 columns) and any columns added later — while
# still issuing few enough round trips for a large seed script to stay fast.
MAX_INSERT_BIND_PARAMS = 30000


class TelemetryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def batch_insert_idempotent(self, rows: Sequence[dict[str, Any]]) -> int:
        """`INSERT ... ON CONFLICT (event_id, source_timestamp) DO NOTHING` — the
        idempotency mechanism for at-least-once delivery (ADR-053). Returns the number of
        rows actually inserted (i.e. excluding duplicates already present).

        Chunks `rows` into bounded-size inserts so the bind-parameter count
        (rows-per-chunk * columns-per-row) never approaches PostgreSQL/asyncpg's ~65535
        parameter ceiling — a single flagship-story or bulk-telemetry seed can easily carry
        tens of thousands of rows, which as one statement blows well past that limit."""
        if not rows:
            return 0
        columns_per_row = len(rows[0])
        batch_size = max(1, MAX_INSERT_BIND_PARAMS // columns_per_row)
        inserted = 0
        for offset in range(0, len(rows), batch_size):
            chunk = rows[offset : offset + batch_size]
            # `Telemetry.__table__` (Core), not the ORM class: a Core insert resolves
            # `.values()` keys as raw DB column names (so `"metadata"` means the `metadata`
            # column), whereas `pg_insert(Telemetry)` triggers SQLAlchemy 2.0's ORM-enabled
            # insert, which resolves keys as Python attribute names and collides with
            # `Telemetry.metadata` (the inherited `Base.metadata` registry, not the mapped
            # `metadata_` column).
            insert_stmt = pg_insert(Telemetry.__table__).values(list(chunk))  # type: ignore[arg-type]
            returning_stmt = insert_stmt.on_conflict_do_nothing(
                constraint="pk_telemetry"
            ).returning(Telemetry.event_id)
            result = await self.session.execute(returning_stmt)
            inserted += len(result.fetchall())
        return inserted

    async def get_by_sensor_time_range(
        self,
        tenant_id: uuid.UUID,
        sensor_id: uuid.UUID,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        measurement_type: SensorType | None = None,
        limit: int = DEFAULT_QUERY_LIMIT,
    ) -> list[Telemetry]:
        clauses = [Telemetry.tenant_id == tenant_id, Telemetry.sensor_id == sensor_id]
        if start is not None:
            clauses.append(Telemetry.source_timestamp >= start)
        if end is not None:
            clauses.append(Telemetry.source_timestamp <= end)
        if measurement_type is not None:
            clauses.append(Telemetry.measurement_type == measurement_type)
        stmt = (
            select(Telemetry)
            .where(*clauses)
            .order_by(Telemetry.source_timestamp.desc())
            .limit(min(limit, MAX_QUERY_LIMIT))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_machine_time_range(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        measurement_type: SensorType | None = None,
        limit: int = DEFAULT_QUERY_LIMIT,
    ) -> list[Telemetry]:
        clauses = [Telemetry.tenant_id == tenant_id, Telemetry.machine_id == machine_id]
        if start is not None:
            clauses.append(Telemetry.source_timestamp >= start)
        if end is not None:
            clauses.append(Telemetry.source_timestamp <= end)
        if measurement_type is not None:
            clauses.append(Telemetry.measurement_type == measurement_type)
        stmt = (
            select(Telemetry)
            .where(*clauses)
            .order_by(Telemetry.source_timestamp.desc())
            .limit(min(limit, MAX_QUERY_LIMIT))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_by_sensor(
        self, tenant_id: uuid.UUID, sensor_id: uuid.UUID
    ) -> Telemetry | None:
        stmt = (
            select(Telemetry)
            .where(Telemetry.tenant_id == tenant_id, Telemetry.sensor_id == sensor_id)
            .order_by(Telemetry.source_timestamp.desc())
            .limit(1)
        )
        result: Telemetry | None = await self.session.scalar(stmt)
        return result

    async def find_duplicate_candidates(
        self,
        tenant_id: uuid.UUID,
        sensor_id: uuid.UUID,
        *,
        source_timestamp: datetime,
        value: float | None,
        exclude_event_id: uuid.UUID,
        lookback_start: datetime,
    ) -> list[uuid.UUID]:
        """Same sensor/source_timestamp/value under a different event_id, within the policy
        lookback window (Phase 7 `ordering.check_duplicate_pattern`'s candidate query — see
        that module's docstring for why this is a soft signal, not a rejection). Uses the
        existing `ix_telemetry_tenant_sensor_time` index (tenant_id, sensor_id,
        source_timestamp DESC)."""
        clauses = [
            Telemetry.tenant_id == tenant_id,
            Telemetry.sensor_id == sensor_id,
            Telemetry.source_timestamp == source_timestamp,
            Telemetry.source_timestamp >= lookback_start,
            Telemetry.event_id != exclude_event_id,
        ]
        clauses.append(Telemetry.value.is_(None) if value is None else Telemetry.value == value)
        stmt = select(Telemetry.event_id).where(*clauses)
        result = await self.session.execute(stmt)
        return [row[0] for row in result.all()]

    async def count(self, tenant_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(Telemetry).where(Telemetry.tenant_id == tenant_id)
        result = await self.session.scalar(stmt)
        return result or 0
