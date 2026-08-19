from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.product_metrics.models import Metric, NorthStarResult, ProductMetricsResult
from app.product_metrics.north_star import compute_north_star
from app.product_metrics.supporting_metrics import compute_supporting_metrics


class ProductMetricsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def north_star(self, tenant_id: uuid.UUID) -> NorthStarResult:
        return await compute_north_star(self._session, tenant_id)

    async def supporting_metrics(self, tenant_id: uuid.UUID) -> list[Metric]:
        return await compute_supporting_metrics(self._session, tenant_id)

    async def all_metrics(self, tenant_id: uuid.UUID) -> ProductMetricsResult:
        north_star = await self.north_star(tenant_id)
        supporting = await self.supporting_metrics(tenant_id)
        return ProductMetricsResult(
            north_star=north_star.metric,
            supporting=supporting,
            generated_at=datetime.now(UTC),
        )
