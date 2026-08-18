from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session
from app.api.schemas.common import PaginatedResponse
from app.api.schemas.site import SiteCreateRequest, SiteResponse
from app.domain.models import Tenant
from app.repositories.pagination import PageParams
from app.services.site_service import SiteCreate, SiteService

router = APIRouter(prefix="/sites", tags=["sites"])


@router.get("", response_model=PaginatedResponse[SiteResponse])
async def list_sites(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[SiteResponse]:
    service = SiteService(session)
    page = await service.list(tenant.id, params=PageParams(limit=limit, offset=offset))
    items = [SiteResponse.model_validate(item) for item in page.items]
    return PaginatedResponse.from_page(page, items)


@router.post("", response_model=SiteResponse, status_code=status.HTTP_201_CREATED)
async def create_site(
    body: SiteCreateRequest,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SiteResponse:
    service = SiteService(session)
    site = await service.create(
        tenant.id,
        SiteCreate(
            customer_account_id=body.customer_account_id,
            name=body.name,
            code=body.code,
            country=body.country,
            city=body.city,
            timezone=body.timezone,
            status=body.status,
            metadata_=body.metadata,
        ),
    )
    return SiteResponse.model_validate(site)


@router.get("/{site_id}", response_model=SiteResponse)
async def get_site(
    site_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SiteResponse:
    service = SiteService(session)
    site = await service.get(tenant.id, site_id)
    return SiteResponse.model_validate(site)
