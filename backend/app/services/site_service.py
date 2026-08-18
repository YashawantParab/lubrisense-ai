from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import CommercialStatus, OperationalStatus
from app.domain.models import Site
from app.repositories.customer_account import CustomerAccountRepository
from app.repositories.pagination import Page, PageParams
from app.repositories.site import SiteRepository
from app.services.errors import ConflictError, InvalidHierarchyError, NotFoundError


@dataclass(frozen=True)
class SiteCreate:
    customer_account_id: uuid.UUID
    name: str
    code: str
    country: str | None = None
    city: str | None = None
    timezone: str | None = None
    status: OperationalStatus = OperationalStatus.ACTIVE
    metadata_: dict[str, Any] | None = None


class SiteService:
    def __init__(self, session: AsyncSession) -> None:
        self._sites = SiteRepository(session)
        self._customers = CustomerAccountRepository(session)

    async def create(self, tenant_id: uuid.UUID, data: SiteCreate) -> Site:
        customer = await self._customers.get(tenant_id, data.customer_account_id)
        if customer is None:
            raise InvalidHierarchyError(
                "CUSTOMER_ACCOUNT_NOT_FOUND_FOR_SITE",
                "customer_account_id does not reference a customer account in this tenant.",
            )
        if customer.commercial_status == CommercialStatus.ENDED:
            raise InvalidHierarchyError(
                "CUSTOMER_ACCOUNT_ENDED",
                "Cannot add a site to a customer account whose commercial status is ENDED.",
            )
        existing = await self._sites.get_by_code(tenant_id, data.code)
        if existing is not None:
            raise ConflictError(
                "SITE_CODE_TAKEN", f"A site with code '{data.code}' already exists for this tenant."
            )
        site = Site(
            tenant_id=tenant_id,
            customer_account_id=data.customer_account_id,
            name=data.name,
            code=data.code,
            country=data.country,
            city=data.city,
            timezone=data.timezone,
            status=data.status,
            metadata_=data.metadata_ or {},
        )
        return await self._sites.add(site)

    async def get(self, tenant_id: uuid.UUID, site_id: uuid.UUID) -> Site:
        site = await self._sites.get(tenant_id, site_id)
        if site is None:
            raise NotFoundError("SITE_NOT_FOUND", "Site not found.")
        return site

    async def list(self, tenant_id: uuid.UUID, *, params: PageParams | None = None) -> Page[Site]:
        return await self._sites.list(tenant_id, params=params)
