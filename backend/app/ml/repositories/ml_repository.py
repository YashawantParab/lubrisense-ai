"""`MLInferenceResult` repository — tenant-scoped, append-only (results are never updated
in place; a re-inference at a later `as_of_timestamp` is a new row)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select

from app.domain.models import MLInferenceResult
from app.repositories.base import TenantScopedRepository


class MLInferenceResultRepository(TenantScopedRepository[MLInferenceResult]):
    model = MLInferenceResult

    async def insert(self, result: MLInferenceResult) -> MLInferenceResult:
        self.session.add(result)
        await self.session.flush()
        return result

    async def latest_for_machine(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID, model_id: str
    ) -> MLInferenceResult | None:
        stmt = (
            select(MLInferenceResult)
            .where(
                MLInferenceResult.tenant_id == tenant_id,
                MLInferenceResult.machine_id == machine_id,
                MLInferenceResult.model_id == model_id,
            )
            .order_by(MLInferenceResult.as_of_timestamp.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_machine(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        *,
        model_id: str | None,
        start: datetime | None,
        end: datetime | None,
        limit: int,
    ) -> list[MLInferenceResult]:
        stmt = select(MLInferenceResult).where(
            MLInferenceResult.tenant_id == tenant_id,
            MLInferenceResult.machine_id == machine_id,
        )
        if model_id is not None:
            stmt = stmt.where(MLInferenceResult.model_id == model_id)
        if start is not None:
            stmt = stmt.where(MLInferenceResult.as_of_timestamp >= start)
        if end is not None:
            stmt = stmt.where(MLInferenceResult.as_of_timestamp <= end)
        stmt = stmt.order_by(MLInferenceResult.as_of_timestamp.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
