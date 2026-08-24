"""Lubrication Efficiency Intelligence API, Pass 1 (Phase-post-roadmap capability
extension — docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md, ADR-176). Kept visibly separate
from `app.api.v1.baselines`/`app.api.v1.ml` — energy-assessment output here is evidence
(an observed deviation from contextual expectation), never a lubrication diagnosis or
maintenance decision; see docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md's product
definition. No lubrication-attribution, carbon, or decision-impact fields exist on this
API yet — deliberately deferred to a later pass."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session
from app.api.schemas.energy import EnergyAssessmentResponse
from app.baselines.config.policy import load_baseline_policy
from app.domain.models import Tenant
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
