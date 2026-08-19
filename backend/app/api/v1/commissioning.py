"""Tenant-scoped Phase 30 commissioning API — a guided demo onboarding workflow, never
real physical device discovery. See docs/COMMISSIONING.md "Purpose"."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session, require_permission
from app.api.schemas.commissioning import (
    AddSensorRequest,
    AssignGatewayRequest,
    CommissioningSessionResponse,
    StartCommissioningRequest,
)
from app.api.schemas.sensor import SensorResponse
from app.audit.service import AuditActor
from app.auth.models import Principal
from app.auth.permissions import Permission
from app.commissioning.service import CommissioningService, InvalidCommissioningTransitionError
from app.domain.models import Tenant
from app.services.errors import NotFoundError

router = APIRouter(prefix="/commissioning", tags=["commissioning"])


@router.post(
    "/sessions",
    response_model=CommissioningSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_session(
    body: StartCommissioningRequest,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[Principal, require_permission(Permission.ASSET_MANAGE)],
) -> CommissioningSessionResponse:
    service = CommissioningService(session)
    commissioning_session = await service.start_session(
        tenant.id,
        production_line_id=body.production_line_id,
        name=body.name,
        asset_code=body.asset_code,
        machine_type=body.machine_type,
        actor=AuditActor.from_principal(principal),
    )
    return CommissioningSessionResponse.model_validate(commissioning_session)


@router.get("/sessions", response_model=list[CommissioningSessionResponse])
async def list_sessions(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[CommissioningSessionResponse]:
    service = CommissioningService(session)
    sessions = await service.list_sessions(tenant.id)
    return [CommissioningSessionResponse.model_validate(s) for s in sessions]


@router.get("/sessions/{session_id}", response_model=CommissioningSessionResponse)
async def get_session(
    session_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CommissioningSessionResponse:
    service = CommissioningService(session)
    try:
        commissioning_session = await service.get(tenant.id, session_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return CommissioningSessionResponse.model_validate(commissioning_session)


@router.post("/sessions/{session_id}/sensors", response_model=SensorResponse)
async def add_sensor(
    session_id: uuid.UUID,
    body: AddSensorRequest,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[Principal, require_permission(Permission.ASSET_MANAGE)],
) -> SensorResponse:
    service = CommissioningService(session)
    try:
        sensor = await service.add_sensor(
            tenant.id,
            session_id,
            sensor_type=body.sensor_type,
            sensor_code=body.sensor_code,
            name=body.name,
            unit=body.unit,
            actor=AuditActor.from_principal(principal),
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except InvalidCommissioningTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return SensorResponse.model_validate(sensor)


@router.post("/sessions/{session_id}/gateway", response_model=CommissioningSessionResponse)
async def assign_gateway(
    session_id: uuid.UUID,
    body: AssignGatewayRequest,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[Principal, require_permission(Permission.ASSET_MANAGE)],
) -> CommissioningSessionResponse:
    service = CommissioningService(session)
    try:
        commissioning_session = await service.assign_gateway(
            tenant.id,
            session_id,
            gateway_id=body.gateway_id,
            actor=AuditActor.from_principal(principal),
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return CommissioningSessionResponse.model_validate(commissioning_session)


@router.post("/sessions/{session_id}/validate", response_model=CommissioningSessionResponse)
async def validate_session(
    session_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _principal: Annotated[Principal, require_permission(Permission.ASSET_MANAGE)],
) -> CommissioningSessionResponse:
    service = CommissioningService(session)
    try:
        commissioning_session = await service.validate(tenant.id, session_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return CommissioningSessionResponse.model_validate(commissioning_session)


@router.post("/sessions/{session_id}/complete", response_model=CommissioningSessionResponse)
async def complete_session(
    session_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[Principal, require_permission(Permission.ASSET_MANAGE)],
) -> CommissioningSessionResponse:
    service = CommissioningService(session)
    try:
        commissioning_session = await service.complete(
            tenant.id, session_id, actor=AuditActor.from_principal(principal)
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except InvalidCommissioningTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return CommissioningSessionResponse.model_validate(commissioning_session)
