from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session
from app.api.schemas.common import PaginatedResponse
from app.api.schemas.plant import PlantCreateRequest, PlantResponse
from app.domain.models import Tenant
from app.repositories.pagination import PageParams
from app.services.plant_service import PlantCreate, PlantService

router = APIRouter(prefix="/plants", tags=["plants"])


@router.get("", response_model=PaginatedResponse[PlantResponse])
async def list_plants(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[PlantResponse]:
    service = PlantService(session)
    page = await service.list(tenant.id, params=PageParams(limit=limit, offset=offset))
    items = [PlantResponse.model_validate(item) for item in page.items]
    return PaginatedResponse.from_page(page, items)


@router.post("", response_model=PlantResponse, status_code=status.HTTP_201_CREATED)
async def create_plant(
    body: PlantCreateRequest,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PlantResponse:
    service = PlantService(session)
    plant = await service.create(
        tenant.id,
        PlantCreate(
            site_id=body.site_id,
            name=body.name,
            code=body.code,
            plant_type=body.plant_type,
            status=body.status,
            metadata_=body.metadata,
        ),
    )
    return PlantResponse.model_validate(plant)


@router.get("/{plant_id}", response_model=PlantResponse)
async def get_plant(
    plant_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PlantResponse:
    service = PlantService(session)
    plant = await service.get(tenant.id, plant_id)
    return PlantResponse.model_validate(plant)
