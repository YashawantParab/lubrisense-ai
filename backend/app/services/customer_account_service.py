from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import CommercialStatus, ServiceTier
from app.domain.models import CustomerAccount
from app.repositories.customer_account import CustomerAccountRepository
from app.repositories.pagination import Page, PageParams
from app.services.errors import ConflictError, NotFoundError


@dataclass(frozen=True)
class CustomerAccountCreate:
    name: str
    code: str
    service_tier: ServiceTier
    industry: str | None = None
    region: str | None = None
    country: str | None = None
    commercial_status: CommercialStatus = CommercialStatus.PROSPECT
    contract_start: date | None = None
    contract_end: date | None = None
    metadata_: dict[str, Any] | None = None


class CustomerAccountService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = CustomerAccountRepository(session)

    async def create(self, tenant_id: uuid.UUID, data: CustomerAccountCreate) -> CustomerAccount:
        existing = await self._repo.get_by_code(tenant_id, data.code)
        if existing is not None:
            raise ConflictError(
                "CUSTOMER_ACCOUNT_CODE_TAKEN",
                f"A customer account with code '{data.code}' already exists for this tenant.",
            )
        customer = CustomerAccount(
            tenant_id=tenant_id,
            name=data.name,
            code=data.code,
            service_tier=data.service_tier,
            industry=data.industry,
            region=data.region,
            country=data.country,
            commercial_status=data.commercial_status,
            contract_start=data.contract_start,
            contract_end=data.contract_end,
            metadata_=data.metadata_ or {},
        )
        return await self._repo.add(customer)

    async def get(self, tenant_id: uuid.UUID, customer_account_id: uuid.UUID) -> CustomerAccount:
        customer = await self._repo.get(tenant_id, customer_account_id)
        if customer is None:
            raise NotFoundError("CUSTOMER_ACCOUNT_NOT_FOUND", "Customer account not found.")
        return customer

    async def list(
        self, tenant_id: uuid.UUID, *, params: PageParams | None = None
    ) -> Page[CustomerAccount]:
        return await self._repo.list(tenant_id, params=params)
