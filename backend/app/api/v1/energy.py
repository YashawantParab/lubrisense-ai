"""Lubrication Efficiency Intelligence API, Pass 1 + Pass 2 + Pass 3 + Pass 4
(post-roadmap capability extension — docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md,
ADR-176). Kept visibly separate from `app.api.v1.baselines`/`app.api.v1.ml` —
energy-assessment/attribution/outcome/carbon output here is evidence and operational
estimates (an observed deviation, how strongly evidence supports a lubrication-related
explanation, whether a completed intervention's outcome qualifies, an estimated CO2e
impact from a qualified outcome and a configured factor), never a lubrication diagnosis,
maintenance decision, or audited corporate carbon-accounting claim; see the design doc's
product definition and claim-terminology sections."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session, require_permission
from app.api.schemas.attribution import AttributionResponse
from app.api.schemas.carbon import (
    CarbonImpactEstimateResponse,
    ConfigureEmissionFactorRequest,
    SiteEmissionFactorResponse,
)
from app.api.schemas.energy import EnergyAssessmentResponse
from app.api.schemas.energy_outcome import EnergyOutcomeVerificationResponse
from app.audit.service import AuditActor, AuditService
from app.auth.models import Principal
from app.auth.permissions import Permission
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
from app.energy.services.carbon_query_service import (
    CarbonQueryEstimateNotFoundError,
    CarbonQueryMachineNotFoundError,
    CarbonQueryService,
)
from app.energy.services.carbon_service import (
    CarbonOutcomeNotFoundError,
    CarbonService,
    CarbonSiteNotResolvedError,
)
from app.energy.services.emission_factor_service import (
    EmissionFactorInvalidError,
    EmissionFactorService,
    EmissionFactorSiteNotFoundError,
)
from app.energy.services.energy_assessment_service import (
    EnergyAssessmentService,
    EnergyMachineNotFoundError,
    EnergyPowerSensorNotFoundError,
)
from app.energy.services.energy_outcome_query_service import (
    EnergyOutcomeQueryMachineNotFoundError,
    EnergyOutcomeQueryService,
    EnergyOutcomeQueryVerificationNotFoundError,
)
from app.energy.services.energy_outcome_service import (
    EnergyOutcomeMachineNotFoundError,
    EnergyOutcomeNoInterventionError,
    EnergyOutcomeNoPowerSensorError,
    EnergyOutcomeService,
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


@router.get("/outcomes/fleet-latest", response_model=list[EnergyOutcomeVerificationResponse])
async def get_fleet_latest_energy_outcome(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[EnergyOutcomeVerificationResponse]:
    service = EnergyOutcomeQueryService(session)
    results = await service.fleet_latest(tenant.id)
    return [EnergyOutcomeVerificationResponse.model_validate(r) for r in results]


@router.get("/outcomes/{verification_id}", response_model=EnergyOutcomeVerificationResponse)
async def get_energy_outcome_by_id(
    verification_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> EnergyOutcomeVerificationResponse:
    service = EnergyOutcomeQueryService(session)
    try:
        result = await service.get(tenant.id, verification_id)
    except EnergyOutcomeQueryVerificationNotFoundError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Energy outcome verification not found."
        ) from exc
    return EnergyOutcomeVerificationResponse.model_validate(result)


@router.get(
    "/machines/{machine_id}/outcomes", response_model=list[EnergyOutcomeVerificationResponse]
)
async def get_energy_outcome_history(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    start: datetime | None = None,
    end: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[EnergyOutcomeVerificationResponse]:
    service = EnergyOutcomeQueryService(session)
    try:
        results = await service.history(tenant.id, machine_id, start=start, end=end, limit=limit)
    except EnergyOutcomeQueryMachineNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found.") from exc
    return [EnergyOutcomeVerificationResponse.model_validate(r) for r in results]


@router.get(
    "/machines/{machine_id}/outcomes/latest", response_model=EnergyOutcomeVerificationResponse
)
async def get_latest_energy_outcome(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> EnergyOutcomeVerificationResponse:
    service = EnergyOutcomeService(session, _POLICY)
    try:
        result = await service.assess_machine(tenant.id, machine_id)
    except EnergyOutcomeMachineNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found.") from exc
    except EnergyOutcomeNoInterventionError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No completed maintenance intervention exists for this machine yet — this is "
            "an active energy opportunity, not yet an outcome to verify.",
        ) from exc
    except EnergyOutcomeNoPowerSensorError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No machine-power sensor commissioned for this machine."
        ) from exc
    return EnergyOutcomeVerificationResponse.model_validate(result)


@router.get("/sites/{site_id}/emission-factor", response_model=SiteEmissionFactorResponse | None)
async def get_site_emission_factor(
    site_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SiteEmissionFactorResponse | None:
    service = EmissionFactorService(session)
    try:
        factor = await service.get_active(tenant.id, site_id)
    except EmissionFactorSiteNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found.") from exc
    return SiteEmissionFactorResponse.model_validate(factor) if factor is not None else None


@router.post(
    "/sites/{site_id}/emission-factor",
    response_model=SiteEmissionFactorResponse,
    status_code=status.HTTP_201_CREATED,
)
async def configure_site_emission_factor(
    site_id: uuid.UUID,
    body: ConfigureEmissionFactorRequest,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[Principal, require_permission(Permission.ADMIN_CONFIG)],
) -> SiteEmissionFactorResponse:
    """`ADMIN_CONFIG`-gated (Phase 24 RBAC) and audited — mirrors
    `app.api.v1.maintenance`'s own `_audit_case` convention for a config-governed write."""
    service = EmissionFactorService(session)
    try:
        factor = await service.configure(
            tenant.id,
            site_id,
            factor_value=body.factor_value,
            source_name=body.source_name,
            source_reference=body.source_reference,
            jurisdiction=body.jurisdiction,
            provenance=body.provenance,
            method=body.method,
        )
    except EmissionFactorSiteNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found.") from exc
    except EmissionFactorInvalidError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    await AuditService(session).record(
        tenant.id,
        actor=AuditActor.from_principal(principal),
        action="emission_factor.configure",
        entity_type="site_emission_factor",
        entity_id=factor.id,
        source="api.energy",
        after_summary=f"{body.factor_value} kg_co2e_per_kwh ({body.source_name})",
    )
    return SiteEmissionFactorResponse.model_validate(factor)


@router.get("/outcomes/{verification_id}/carbon", response_model=CarbonImpactEstimateResponse)
async def get_carbon_estimate_for_outcome(
    verification_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CarbonImpactEstimateResponse:
    service = CarbonService(session)
    try:
        estimate = await service.assess_for_outcome(tenant.id, verification_id)
    except CarbonOutcomeNotFoundError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Energy outcome verification not found."
        ) from exc
    except CarbonSiteNotResolvedError as exc:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Machine's site could not be resolved.",
        ) from exc
    return CarbonImpactEstimateResponse.model_validate(estimate)


@router.get("/carbon/fleet-latest", response_model=list[CarbonImpactEstimateResponse])
async def get_fleet_latest_carbon(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[CarbonImpactEstimateResponse]:
    service = CarbonQueryService(session)
    results = await service.fleet_latest(tenant.id)
    return [CarbonImpactEstimateResponse.model_validate(r) for r in results]


@router.get("/machines/{machine_id}/carbon/latest", response_model=CarbonImpactEstimateResponse)
async def get_latest_carbon_for_machine(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CarbonImpactEstimateResponse:
    service = CarbonQueryService(session)
    try:
        estimate = await service.latest_for_machine(tenant.id, machine_id)
    except CarbonQueryMachineNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found.") from exc
    if estimate is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No carbon estimate has been computed for this machine yet."
        )
    return CarbonImpactEstimateResponse.model_validate(estimate)


@router.get("/carbon/{estimate_id}", response_model=CarbonImpactEstimateResponse)
async def get_carbon_estimate_by_id(
    estimate_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CarbonImpactEstimateResponse:
    service = CarbonQueryService(session)
    try:
        estimate = await service.get(tenant.id, estimate_id)
    except CarbonQueryEstimateNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Carbon estimate not found.") from exc
    return CarbonImpactEstimateResponse.model_validate(estimate)
