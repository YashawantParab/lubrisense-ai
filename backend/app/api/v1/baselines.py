"""Baseline read API (Phase 8 brief §32) — tenant-scoped via `get_current_tenant`, same
convention as `app/api/v1/data_quality.py`."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session
from app.api.schemas.baselines import (
    BaselineProfileResponse,
    CurrentBaselineResponse,
    DeviationResponse,
    MachineBaselinesResponse,
    ReadinessResponse,
    SensorBaselinesResponse,
    TenantBaselineSummaryResponse,
)
from app.baselines.config.policy import load_baseline_policy
from app.baselines.services.query_service import (
    BaselineQueryService,
    MachineNotFoundError,
    SensorNotFoundError,
)
from app.baselines.services.summary_service import Readiness
from app.domain.models import Tenant

router = APIRouter(prefix="/baselines", tags=["baselines"])

# Loaded once at import time, mirroring `app.data_quality.config.policy`'s per-process
# load — the policy file only changes via a deployment, not per-request.
_POLICY = load_baseline_policy()


def _readiness_response(readiness: Readiness) -> ReadinessResponse:
    return ReadinessResponse(
        label=readiness.label,
        active_count=readiness.active_count,
        building_count=readiness.building_count,
        insufficient_data_count=readiness.insufficient_data_count,
        stale_count=readiness.stale_count,
        invalidated_count=readiness.invalidated_count,
    )


@router.get("/sensors/{sensor_id}", response_model=SensorBaselinesResponse)
async def get_sensor_baselines(
    sensor_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SensorBaselinesResponse:
    service = BaselineQueryService(session, _POLICY)
    try:
        profiles, readiness = await service.list_for_sensor(tenant.id, sensor_id)
    except SensorNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sensor not found.") from exc
    return SensorBaselinesResponse(
        sensor_id=sensor_id,
        readiness=_readiness_response(readiness),
        profiles=[BaselineProfileResponse.model_validate(p) for p in profiles],
    )


@router.get("/sensors/{sensor_id}/current", response_model=CurrentBaselineResponse)
async def get_current_baseline(
    sensor_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    operating_state: str | None = None,
    cycle_phase: str | None = None,
    value: float | None = Query(
        default=None, description="Reading to evaluate against the resolved baseline"
    ),
) -> CurrentBaselineResponse:
    service = BaselineQueryService(session, _POLICY)
    try:
        lookup = await service.get_current(
            tenant.id,
            sensor_id,
            operating_state=operating_state,
            cycle_phase=cycle_phase,
            value=value,
        )
    except SensorNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sensor not found.") from exc
    return CurrentBaselineResponse(
        sensor_id=sensor_id,
        source=lookup.resolved.source,
        profile=BaselineProfileResponse.model_validate(lookup.resolved.profile)
        if lookup.resolved.profile is not None
        else None,
        deviation=DeviationResponse(**lookup.deviation.__dict__) if lookup.deviation else None,
    )


@router.get("/machines/{machine_id}", response_model=MachineBaselinesResponse)
async def get_machine_baselines(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MachineBaselinesResponse:
    service = BaselineQueryService(session, _POLICY)
    try:
        profiles, readiness = await service.list_for_machine(tenant.id, machine_id)
    except MachineNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found.") from exc
    return MachineBaselinesResponse(
        machine_id=machine_id,
        readiness=_readiness_response(readiness),
        profiles=[BaselineProfileResponse.model_validate(p) for p in profiles],
    )


@router.get("/summary", response_model=TenantBaselineSummaryResponse)
async def get_baseline_summary(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TenantBaselineSummaryResponse:
    service = BaselineQueryService(session, _POLICY)
    counts = await service.tenant_summary(tenant.id)
    return TenantBaselineSummaryResponse(
        profiles_by_state=counts, total_profiles=sum(counts.values())
    )
