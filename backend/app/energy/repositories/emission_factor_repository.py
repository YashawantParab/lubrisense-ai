"""`SiteEmissionFactor` repository — tenant-scoped (Lubrication Efficiency Intelligence,
Pass 4, ADR-176)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select

from app.domain.models import SiteEmissionFactor
from app.repositories.base import TenantScopedRepository


class SiteEmissionFactorRepository(TenantScopedRepository[SiteEmissionFactor]):
    model = SiteEmissionFactor

    async def insert(self, factor: SiteEmissionFactor) -> SiteEmissionFactor:
        self.session.add(factor)
        await self.session.flush()
        return factor

    async def get(self, tenant_id: uuid.UUID, factor_id: uuid.UUID) -> SiteEmissionFactor | None:
        stmt = select(SiteEmissionFactor).where(
            SiteEmissionFactor.tenant_id == tenant_id, SiteEmissionFactor.id == factor_id
        )
        result: SiteEmissionFactor | None = await self.session.scalar(stmt)
        return result

    async def active_for_site(
        self, tenant_id: uuid.UUID, site_id: uuid.UUID
    ) -> SiteEmissionFactor | None:
        """The single active factor for a site — `SiteEmissionFactor.factor_type` is
        always `"ELECTRICITY"` in this pass, so no additional filter is needed yet. If
        more than one active row exists (a configuration mistake this reference platform
        does not otherwise prevent), the most recently published one wins, deterministically."""
        stmt = (
            select(SiteEmissionFactor)
            .where(
                SiteEmissionFactor.tenant_id == tenant_id,
                SiteEmissionFactor.site_id == site_id,
                SiteEmissionFactor.is_active.is_(True),
            )
            .order_by(SiteEmissionFactor.effective_from.desc())
            .limit(1)
        )
        result: SiteEmissionFactor | None = await self.session.scalar(stmt)
        return result

    async def list_for_site(
        self, tenant_id: uuid.UUID, site_id: uuid.UUID
    ) -> list[SiteEmissionFactor]:
        stmt = (
            select(SiteEmissionFactor)
            .where(
                SiteEmissionFactor.tenant_id == tenant_id,
                SiteEmissionFactor.site_id == site_id,
            )
            .order_by(SiteEmissionFactor.effective_from.desc())
        )
        return list((await self.session.scalars(stmt)).all())

    async def deactivate_active_for_site(
        self, tenant_id: uuid.UUID, site_id: uuid.UUID, *, as_of: datetime
    ) -> None:
        """Marks any currently-active factor(s) for this site inactive and closes their
        `effective_to` — called immediately before inserting a replacement, so at most one
        factor is ever active per site at a time (never mutates `factor_value` in place;
        see class docstring)."""
        existing = await self.list_for_site(tenant_id, site_id)
        for row in existing:
            if row.is_active:
                row.is_active = False
                if row.effective_to is None:
                    row.effective_to = as_of
        await self.session.flush()
