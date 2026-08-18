from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session
from app.api.schemas.common import PaginatedResponse
from app.api.schemas.production_line import ProductionLineCreateRequest, ProductionLineResponse
from app.domain.models import Tenant
from app.repositories.pagination import PageParams
from app.services.production_line_service import ProductionLineCreate, ProductionLineService

router = APIRouter(prefix="/production-lines", tags=["production-lines"])


@router.get("", response_model=PaginatedResponse[ProductionLineResponse])
async def list_production_lines(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[ProductionLineResponse]:
    service = ProductionLineService(session)
    page = await service.list(tenant.id, params=PageParams(limit=limit, offset=offset))
    items = [ProductionLineResponse.model_validate(item) for item in page.items]
    return PaginatedResponse.from_page(page, items)


@router.post("", response_model=ProductionLineResponse, status_code=status.HTTP_201_CREATED)
async def create_production_line(
    body: ProductionLineCreateRequest,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProductionLineResponse:
    service = ProductionLineService(session)
    line = await service.create(
        tenant.id,
        ProductionLineCreate(
            plant_id=body.plant_id,
            name=body.name,
            code=body.code,
            description=body.description,
            status=body.status,
            criticality=body.criticality,
            metadata_=body.metadata,
        ),
    )
    return ProductionLineResponse.model_validate(line)


@router.get("/{production_line_id}", response_model=ProductionLineResponse)
async def get_production_line(
    production_line_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProductionLineResponse:
    service = ProductionLineService(session)
    line = await service.get(tenant.id, production_line_id)
    return ProductionLineResponse.model_validate(line)
