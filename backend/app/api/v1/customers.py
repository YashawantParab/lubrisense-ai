from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session
from app.api.schemas.common import PaginatedResponse
from app.api.schemas.customer_account import CustomerAccountCreateRequest, CustomerAccountResponse
from app.domain.models import Tenant
from app.repositories.pagination import PageParams
from app.services.customer_account_service import CustomerAccountCreate, CustomerAccountService

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=PaginatedResponse[CustomerAccountResponse])
async def list_customers(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[CustomerAccountResponse]:
    service = CustomerAccountService(session)
    page = await service.list(tenant.id, params=PageParams(limit=limit, offset=offset))
    items = [CustomerAccountResponse.model_validate(item) for item in page.items]
    return PaginatedResponse.from_page(page, items)


@router.post("", response_model=CustomerAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    body: CustomerAccountCreateRequest,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CustomerAccountResponse:
    service = CustomerAccountService(session)
    customer = await service.create(
        tenant.id,
        CustomerAccountCreate(
            name=body.name,
            code=body.code,
            service_tier=body.service_tier,
            industry=body.industry,
            region=body.region,
            country=body.country,
            commercial_status=body.commercial_status,
            contract_start=body.contract_start,
            contract_end=body.contract_end,
            metadata_=body.metadata,
        ),
    )
    return CustomerAccountResponse.model_validate(customer)


@router.get("/{customer_id}", response_model=CustomerAccountResponse)
async def get_customer(
    customer_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CustomerAccountResponse:
    service = CustomerAccountService(session)
    customer = await service.get(tenant.id, customer_id)
    return CustomerAccountResponse.model_validate(customer)
