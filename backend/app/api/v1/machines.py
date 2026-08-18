from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session
from app.api.schemas.bearing import BearingResponse
from app.api.schemas.common import PaginatedResponse
from app.api.schemas.lubrication_system import LubricationSystemResponse
from app.api.schemas.machine import MachineCreateRequest, MachineHierarchyResponse, MachineResponse
from app.api.schemas.sensor import SensorResponse
from app.domain.enums import Criticality, MachineStatus, MachineType
from app.domain.models import Tenant
from app.repositories.pagination import PageParams
from app.services.machine_service import MachineCreate, MachineFilters, MachineService

router = APIRouter(prefix="/machines", tags=["machines"])


@router.get("", response_model=PaginatedResponse[MachineResponse])
async def list_machines(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    machine_type: MachineType | None = None,
    status_: Annotated[MachineStatus | None, Query(alias="status")] = None,
    criticality: Criticality | None = None,
    production_line_id: uuid.UUID | None = None,
) -> PaginatedResponse[MachineResponse]:
    service = MachineService(session)
    page = await service.list(
        tenant.id,
        params=PageParams(limit=limit, offset=offset),
        filters=MachineFilters(
            machine_type=machine_type,
            status=status_,
            criticality=criticality,
            production_line_id=production_line_id,
        ),
    )
    items = [MachineResponse.model_validate(item) for item in page.items]
    return PaginatedResponse.from_page(page, items)


@router.post("", response_model=MachineResponse, status_code=status.HTTP_201_CREATED)
async def create_machine(
    body: MachineCreateRequest,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MachineResponse:
    service = MachineService(session)
    machine = await service.create(
        tenant.id,
        MachineCreate(
            production_line_id=body.production_line_id,
            name=body.name,
            asset_code=body.asset_code,
            machine_type=body.machine_type,
            manufacturer=body.manufacturer,
            model=body.model,
            serial_number_demo=body.serial_number_demo,
            installation_date=body.installation_date,
            criticality=body.criticality,
            status=body.status,
            operating_profile=body.operating_profile,
            metadata_=body.metadata,
        ),
    )
    return MachineResponse.model_validate(machine)


@router.get("/{machine_id}", response_model=MachineResponse)
async def get_machine(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MachineResponse:
    service = MachineService(session)
    machine = await service.get(tenant.id, machine_id)
    return MachineResponse.model_validate(machine)


@router.get("/{machine_id}/hierarchy", response_model=MachineHierarchyResponse)
async def get_machine_hierarchy(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MachineHierarchyResponse:
    service = MachineService(session)
    hierarchy = await service.get_hierarchy(tenant.id, machine_id)
    return MachineHierarchyResponse(
        machine=MachineResponse.model_validate(hierarchy.machine),
        bearings=[BearingResponse.model_validate(b) for b in hierarchy.bearings],
        lubrication_systems=[
            LubricationSystemResponse.model_validate(ls) for ls in hierarchy.lubrication_systems
        ],
        sensors=[SensorResponse.model_validate(s) for s in hierarchy.sensors],
    )
