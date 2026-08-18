from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session
from app.api.schemas.common import PaginatedResponse
from app.api.schemas.lubrication_system import (
    LubricationSystemResponse,
    LubricationSystemSummaryResponse,
)
from app.domain.models import Tenant
from app.repositories.pagination import PageParams
from app.services.lubrication_system_service import LubricationSystemService

router = APIRouter(prefix="/lubrication-systems", tags=["lubrication-systems"])


@router.get("", response_model=PaginatedResponse[LubricationSystemSummaryResponse])
async def list_lubrication_systems(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[LubricationSystemSummaryResponse]:
    service = LubricationSystemService(session)
    page = await service.list(tenant.id, params=PageParams(limit=limit, offset=offset))
    items = [LubricationSystemSummaryResponse.model_validate(item) for item in page.items]
    return PaginatedResponse.from_page(page, items)


@router.get("/{lubrication_system_id}", response_model=LubricationSystemResponse)
async def get_lubrication_system(
    lubrication_system_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> LubricationSystemResponse:
    service = LubricationSystemService(session)
    system = await service.get(tenant.id, lubrication_system_id)
    return LubricationSystemResponse.model_validate(system)
