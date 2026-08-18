from __future__ import annotations

import uuid

from sqlalchemy import select

from app.domain.models import Bearing
from app.repositories.base import TenantScopedRepository


class BearingRepository(TenantScopedRepository[Bearing]):
    model = Bearing

    async def list_by_machine(self, tenant_id: uuid.UUID, machine_id: uuid.UUID) -> list[Bearing]:
        stmt = select(Bearing).where(
            Bearing.tenant_id == tenant_id, Bearing.machine_id == machine_id
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
