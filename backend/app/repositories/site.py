from __future__ import annotations

import uuid

from sqlalchemy import select

from app.domain.models import Site
from app.repositories.base import TenantScopedRepository


class SiteRepository(TenantScopedRepository[Site]):
    model = Site

    async def get_by_code(self, tenant_id: uuid.UUID, code: str) -> Site | None:
        stmt = select(Site).where(Site.tenant_id == tenant_id, Site.code == code)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
