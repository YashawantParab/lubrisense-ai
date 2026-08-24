"""Lubrication Efficiency Intelligence API, Pass 1 + Pass 2 (post-roadmap capability
extension — docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md, ADR-176). Kept visibly separate
from `app.api.v1.baselines`/`app.api.v1.ml` — energy-assessment and attribution output
here is evidence (an observed deviation from contextual expectation, and how strongly
independent evidence supports a lubrication-related explanation for it), never a
lubrication diagnosis or maintenance decision; see the design doc's product definition.
No carbon or decision-impact fields exist on this API yet — deliberately deferred."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session
from app.api.schemas.attribution import AttributionResponse
from app.api.schemas.energy import EnergyAssessmentResponse
from app.baselines.config.policy import load_baseline_policy
from app.domain.models import Tenant
from app.energy.services.attribution_query_service import (
    AttributionQueryMachineNotFoundError,
    AttributionQueryService,
)
from app.energy.services.attribution_service import (
    AttributionEnergyAssessmentNotFoundError,
    AttributionMachineNotFoundError,
    AttributionService,
)
from app.energy.services.energy_assessment_service import (
    EnergyAssessmentService,
    EnergyMachineNotFoundError,
    EnergyPowerSensorNotFoundError,
)
from app.energy.services.energy_query_service import (
    EnergyQueryMachineNotFoundError,
    EnergyQueryService,
)

router = APIRouter(prefix="/energy", tags=["energy"])
_POLICY = load_baseline_policy()


@router.get("/fleet-latest", response_model=list[EnergyAssessmentResponse])
async def get_fleet_latest_energy_assessment(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[EnergyAssessmentResponse]:
    service = EnergyQueryService(session)
    results = await service.fleet_latest(tenant.id)
    return [EnergyAssessmentResponse.model_validate(r) for r in results]


@router.get("/machines/{machine_id}/latest", response_model=EnergyAssessmentResponse)
async def get_latest_energy_assessment(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> EnergyAssessmentResponse:
    service = EnergyAssessmentService(session, _POLICY)
    try:
        result = await service.assess_machine(tenant.id, machine_id)
    except EnergyMachineNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found.") from exc
    except EnergyPowerSensorNotFoundError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No machine-power sensor commissioned for this machine."
        ) from exc
    return EnergyAssessmentResponse.model_validate(result)


@router.get("/machines/{machine_id}/history", response_model=list[EnergyAssessmentResponse])
async def get_energy_assessment_history(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    start: datetime | None = None,
    end: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[EnergyAssessmentResponse]:
    service = EnergyQueryService(session)
    try:
        results = await service.history(tenant.id, machine_id, start=start, end=end, limit=limit)
    except EnergyQueryMachineNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found.") from exc
    return [EnergyAssessmentResponse.model_validate(r) for r in results]


@router.get("/attribution/fleet-latest", response_model=list[AttributionResponse])
async def get_fleet_latest_attribution(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[AttributionResponse]:
    service = AttributionQueryService(session)
    results = await service.fleet_latest(tenant.id)
    return [AttributionResponse.model_validate(r) for r in results]


@router.get("/machines/{machine_id}/attribution/latest", response_model=AttributionResponse)
async def get_latest_attribution(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AttributionResponse:
    service = AttributionService(session)
    try:
        result = await service.assess_machine(tenant.id, machine_id)
    except AttributionMachineNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found.") from exc
    except AttributionEnergyAssessmentNotFoundError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No energy assessment exists for this machine yet — "
            "GET .../energy/machines/{machine_id}/latest first.",
        ) from exc
    return AttributionResponse.model_validate(result)


@router.get("/machines/{machine_id}/attribution/history", response_model=list[AttributionResponse])
async def get_attribution_history(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    start: datetime | None = None,
    end: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[AttributionResponse]:
    service = AttributionQueryService(session)
    try:
        results = await service.history(tenant.id, machine_id, start=start, end=end, limit=limit)
    except AttributionQueryMachineNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found.") from exc
    return [AttributionResponse.model_validate(r) for r in results]
