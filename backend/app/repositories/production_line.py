from __future__ import annotations

import uuid

from sqlalchemy import select

from app.domain.models import ProductionLine
from app.repositories.base import TenantScopedRepository


class ProductionLineRepository(TenantScopedRepository[ProductionLine]):
    model = ProductionLine

    async def get_by_code(
        self, tenant_id: uuid.UUID, plant_id: uuid.UUID, code: str
    ) -> ProductionLine | None:
        stmt = select(ProductionLine).where(
            ProductionLine.tenant_id == tenant_id,
            ProductionLine.plant_id == plant_id,
            ProductionLine.code == code,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
