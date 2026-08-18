from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.domain.models import Circuit, LubricationSystem
from app.repositories.base import TenantScopedRepository


class LubricationSystemRepository(TenantScopedRepository[LubricationSystem]):
    model = LubricationSystem

    async def get_with_equipment(
        self, tenant_id: uuid.UUID, lubrication_system_id: uuid.UUID
    ) -> LubricationSystem | None:
        stmt = (
            select(LubricationSystem)
            .where(
                LubricationSystem.tenant_id == tenant_id,
                LubricationSystem.id == lubrication_system_id,
            )
            .options(
                selectinload(LubricationSystem.reservoirs),
                selectinload(LubricationSystem.pumps),
                selectinload(LubricationSystem.controllers),
                selectinload(LubricationSystem.distributors),
                selectinload(LubricationSystem.circuits).selectinload(Circuit.lubrication_points),
            )
        )
        result = await self.session.execute(stmt)
        return result.unique().scalar_one_or_none()
