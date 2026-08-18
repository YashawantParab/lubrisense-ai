from __future__ import annotations

import uuid

from sqlalchemy import select

from app.domain.models import Plant
from app.repositories.base import TenantScopedRepository


class PlantRepository(TenantScopedRepository[Plant]):
    model = Plant

    async def get_by_code(self, tenant_id: uuid.UUID, code: str) -> Plant | None:
        stmt = select(Plant).where(Plant.tenant_id == tenant_id, Plant.code == code)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
