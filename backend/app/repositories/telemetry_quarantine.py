"""Repository for `telemetry_quarantine` (Phase 6 brief §20/§25).

Deliberately not tenant-scoped in the same way as `TenantScopedRepository`: a quarantined
row's `tenant_id` may be unknown, invalid, or missing entirely — that ambiguity is exactly
why the row exists. `insert` has no idempotency requirement (unlike `Telemetry`); a message
that fails validation twice is logged twice, which is acceptable since these rows are for
operator visibility, not the system of record.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import QuarantineReason
from app.domain.models import TelemetryQuarantine

DEFAULT_QUERY_LIMIT = 200
MAX_QUERY_LIMIT = 2000


class QuarantineRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert(
        self,
        *,
        reason: QuarantineReason,
        detail: str,
        raw_payload: str,
        event_id: uuid.UUID | None = None,
        tenant_id: uuid.UUID | None = None,
        sensor_id: uuid.UUID | None = None,
        gateway_id: str | None = None,
        kafka_topic: str | None = None,
        kafka_partition: int | None = None,
        kafka_offset: int | None = None,
    ) -> TelemetryQuarantine:
        row = TelemetryQuarantine(
            reason=reason,
            detail=detail,
            raw_payload=raw_payload,
            event_id=event_id,
            tenant_id=tenant_id,
            sensor_id=sensor_id,
            gateway_id=gateway_id,
            kafka_topic=kafka_topic,
            kafka_partition=kafka_partition,
            kafka_offset=kafka_offset,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def list_recent(
        self, *, tenant_id: uuid.UUID | None = None, limit: int = DEFAULT_QUERY_LIMIT
    ) -> list[TelemetryQuarantine]:
        clauses = []
        if tenant_id is not None:
            clauses.append(TelemetryQuarantine.tenant_id == tenant_id)
        stmt = (
            select(TelemetryQuarantine)
            .where(*clauses)
            .order_by(TelemetryQuarantine.quarantined_at.desc())
            .limit(min(limit, MAX_QUERY_LIMIT))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
