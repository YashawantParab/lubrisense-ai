from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session
from app.api.schemas.telemetry import TelemetryReadingResponse
from app.domain.enums import SensorType
from app.domain.models import Tenant
from app.services.telemetry_query_service import TelemetryQueryService

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.get("/sensors/{sensor_id}", response_model=list[TelemetryReadingResponse])
async def get_sensor_telemetry(
    sensor_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    start: datetime | None = None,
    end: datetime | None = None,
    measurement_type: SensorType | None = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 200,
) -> list[TelemetryReadingResponse]:
    service = TelemetryQueryService(session)
    readings = await service.get_by_sensor(
        tenant.id, sensor_id, start=start, end=end, measurement_type=measurement_type, limit=limit
    )
    return [TelemetryReadingResponse.model_validate(r) for r in readings]


@router.get("/sensors/{sensor_id}/latest", response_model=TelemetryReadingResponse | None)
async def get_sensor_latest_telemetry(
    sensor_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TelemetryReadingResponse | None:
    service = TelemetryQueryService(session)
    reading = await service.get_latest_by_sensor(tenant.id, sensor_id)
    return TelemetryReadingResponse.model_validate(reading) if reading is not None else None


@router.get("/machines/{machine_id}", response_model=list[TelemetryReadingResponse])
async def get_machine_telemetry(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    start: datetime | None = None,
    end: datetime | None = None,
    measurement_type: SensorType | None = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 200,
) -> list[TelemetryReadingResponse]:
    service = TelemetryQueryService(session)
    readings = await service.get_by_machine(
        tenant.id, machine_id, start=start, end=end, measurement_type=measurement_type, limit=limit
    )
    return [TelemetryReadingResponse.model_validate(r) for r in readings]
