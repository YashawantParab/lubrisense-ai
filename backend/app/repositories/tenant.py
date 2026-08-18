"""TenantRepository — not tenant-scoped itself (Tenant is the scope).

Used only to validate that a tenant context (see app.api.deps.get_tenant_id) refers to a
real, active tenant — never for cross-tenant listing/browsing.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Tenant


class TenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, tenant_id: uuid.UUID) -> Tenant | None:
        result = await self.session.execute(select(Tenant).where(Tenant.id == tenant_id))
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Tenant | None:
        result = await self.session.execute(select(Tenant).where(Tenant.slug == slug))
        return result.scalar_one_or_none()
