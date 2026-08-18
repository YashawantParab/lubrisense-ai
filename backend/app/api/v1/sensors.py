from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session
from app.api.schemas.common import PaginatedResponse
from app.api.schemas.sensor import SensorResponse
from app.domain.enums import SensorStatus, SensorType
from app.domain.models import Tenant
from app.repositories.pagination import PageParams
from app.services.sensor_service import SensorFilters, SensorService

router = APIRouter(prefix="/sensors", tags=["sensors"])


@router.get("", response_model=PaginatedResponse[SensorResponse])
async def list_sensors(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    sensor_type: SensorType | None = None,
    status_: Annotated[SensorStatus | None, Query(alias="status")] = None,
) -> PaginatedResponse[SensorResponse]:
    service = SensorService(session)
    page = await service.list(
        tenant.id,
        params=PageParams(limit=limit, offset=offset),
        filters=SensorFilters(sensor_type=sensor_type, status=status_),
    )
    items = [SensorResponse.model_validate(item) for item in page.items]
    return PaginatedResponse.from_page(page, items)


@router.get("/{sensor_id}", response_model=SensorResponse)
async def get_sensor(
    sensor_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SensorResponse:
    service = SensorService(session)
    sensor = await service.get(tenant.id, sensor_id)
    return SensorResponse.model_validate(sensor)
