from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import LubricationSystem
from app.repositories.lubrication_system import LubricationSystemRepository
from app.repositories.pagination import Page, PageParams
from app.services.errors import NotFoundError


class LubricationSystemService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = LubricationSystemRepository(session)

    async def get(
        self, tenant_id: uuid.UUID, lubrication_system_id: uuid.UUID
    ) -> LubricationSystem:
        system = await self._repo.get_with_equipment(tenant_id, lubrication_system_id)
        if system is None:
            raise NotFoundError("LUBRICATION_SYSTEM_NOT_FOUND", "Lubrication system not found.")
        return system

    async def list(
        self, tenant_id: uuid.UUID, *, params: PageParams | None = None
    ) -> Page[LubricationSystem]:
        return await self._repo.list(tenant_id, params=params)
