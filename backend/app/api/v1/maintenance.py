"""Tenant-scoped Phase 17 maintenance-workflow API. No physical maintenance action is
ever executed automatically — every endpoint here only records what a human
recommended/planned/performed/found. See docs/MAINTENANCE_WORKFLOW.md "Purpose"."""

from __future__ import annotations

import dataclasses
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session, require_permission
from app.api.schemas.cmms import WorkOrderResponse
from app.api.schemas.maintenance import (
    CancelCaseRequest,
    CompleteCaseRequest,
    FeedbackRecordResponse,
    MaintenanceActionResponse,
    MaintenanceCaseResponse,
    PlanCaseRequest,
    RecordActionRequest,
    RecordFindingRequest,
    TechnicianFindingResponse,
)
from app.audit.service import AuditActor, AuditService
from app.auth.models import Principal
from app.auth.permissions import Permission
from app.cmms.services.cmms_service import CMMSService, CMMSUnavailableError
from app.domain.enums import MaintenanceState
from app.domain.models import Tenant
from app.incidents.services.incident_service import IncidentNotFoundError
from app.maintenance.observability import METRICS
from app.maintenance.services.maintenance_service import (
    InvalidMaintenanceTransitionError,
    MaintenanceCaseNotFoundError,
    MaintenanceService,
)

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


class CreateCaseRequest(BaseModel):
    incident_id: uuid.UUID


async def _audit_case(
    session: AsyncSession,
    tenant: Tenant,
    principal: Principal,
    case_id: uuid.UUID,
    action: str,
    reason: str | None = None,
) -> None:
    await AuditService(session).record(
        tenant.id,
        actor=AuditActor.from_principal(principal),
        action=action,
        entity_type="maintenance_case",
        entity_id=case_id,
        source="api.maintenance",
        reason=reason,
    )


@router.get("/cases/metrics")
async def get_maintenance_metrics() -> Response:
    """Registered before `/cases/{case_id}` so the literal path `metrics` is never
    mistaken for a case id."""
    return Response(content=METRICS.render_prometheus_text(), media_type="text/plain")


@router.post("/cases", response_model=MaintenanceCaseResponse, status_code=status.HTTP_201_CREATED)
async def create_case(
    body: CreateCaseRequest,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[Principal, require_permission(Permission.MAINTENANCE_WRITE)],
) -> MaintenanceCaseResponse:
    """Idempotent — returns the existing active case if one is already linked to this
    incident (Phase 17 brief §17.4)."""
    service = MaintenanceService(session)
    try:
        case = await service.create_case_for_incident(tenant.id, body.incident_id)
    except IncidentNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found.") from exc
    except MaintenanceCaseNotFoundError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await _audit_case(session, tenant, principal, case.id, "MAINTENANCE_CASE_CREATED")
    return MaintenanceCaseResponse.model_validate(case)


@router.get("/cases", response_model=list[MaintenanceCaseResponse])
async def list_cases(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    state: MaintenanceState | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[MaintenanceCaseResponse]:
    service = MaintenanceService(session)
    cases = await service.list_cases(tenant.id, state=state, limit=limit)
    return [MaintenanceCaseResponse.model_validate(c) for c in cases]


async def _get_case_or_404(
    service: MaintenanceService, tenant_id: uuid.UUID, case_id: uuid.UUID
) -> MaintenanceCaseResponse:
    try:
        case = await service.get(tenant_id, case_id)
    except MaintenanceCaseNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Maintenance case not found.") from exc
    return MaintenanceCaseResponse.model_validate(case)


@router.get("/cases/{case_id}", response_model=MaintenanceCaseResponse)
async def get_case(
    case_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MaintenanceCaseResponse:
    return await _get_case_or_404(MaintenanceService(session), tenant.id, case_id)


@router.get("/cases/{case_id}/findings", response_model=list[TechnicianFindingResponse])
async def list_findings(
    case_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[TechnicianFindingResponse]:
    service = MaintenanceService(session)
    try:
        findings = await service.list_findings(tenant.id, case_id)
    except MaintenanceCaseNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Maintenance case not found.") from exc
    return [TechnicianFindingResponse.model_validate(f) for f in findings]


@router.get("/cases/{case_id}/actions", response_model=list[MaintenanceActionResponse])
async def list_actions(
    case_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[MaintenanceActionResponse]:
    service = MaintenanceService(session)
    try:
        actions = await service.list_actions(tenant.id, case_id)
    except MaintenanceCaseNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Maintenance case not found.") from exc
    return [MaintenanceActionResponse.model_validate(a) for a in actions]


@router.get("/cases/{case_id}/feedback", response_model=FeedbackRecordResponse | None)
async def get_feedback(
    case_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> FeedbackRecordResponse | None:
    service = MaintenanceService(session)
    try:
        record = await service.get_feedback(tenant.id, case_id)
    except MaintenanceCaseNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Maintenance case not found.") from exc
    return FeedbackRecordResponse.model_validate(record) if record is not None else None


@router.post("/cases/{case_id}/plan", response_model=MaintenanceCaseResponse)
async def plan_case(
    case_id: uuid.UUID,
    body: PlanCaseRequest,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[Principal, require_permission(Permission.MAINTENANCE_WRITE)],
) -> MaintenanceCaseResponse:
    service = MaintenanceService(session)
    try:
        case = await service.plan(tenant.id, case_id, planned_for=body.planned_for)
    except MaintenanceCaseNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Maintenance case not found.") from exc
    except InvalidMaintenanceTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await _audit_case(session, tenant, principal, case_id, "MAINTENANCE_CASE_PLANNED")
    return MaintenanceCaseResponse.model_validate(case)


@router.post("/cases/{case_id}/start", response_model=MaintenanceCaseResponse)
async def start_case(
    case_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[Principal, require_permission(Permission.MAINTENANCE_WRITE)],
) -> MaintenanceCaseResponse:
    service = MaintenanceService(session)
    try:
        case = await service.start(tenant.id, case_id)
    except MaintenanceCaseNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Maintenance case not found.") from exc
    except InvalidMaintenanceTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await _audit_case(session, tenant, principal, case_id, "MAINTENANCE_CASE_STARTED")
    return MaintenanceCaseResponse.model_validate(case)


@router.post("/cases/{case_id}/finding", response_model=TechnicianFindingResponse)
async def record_finding(
    case_id: uuid.UUID,
    body: RecordFindingRequest,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[Principal, require_permission(Permission.MAINTENANCE_WRITE)],
) -> TechnicianFindingResponse:
    service = MaintenanceService(session)
    try:
        finding = await service.record_finding(
            tenant.id,
            case_id,
            result=body.result,
            component=body.component,
            observed_issue=body.observed_issue,
            notes=body.notes,
            technician_identifier=body.technician_identifier,
        )
    except MaintenanceCaseNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Maintenance case not found.") from exc
    except InvalidMaintenanceTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await _audit_case(
        session, tenant, principal, case_id, "MAINTENANCE_FINDING_RECORDED",
        reason=body.result.value,
    )
    return TechnicianFindingResponse.model_validate(finding)


@router.post("/cases/{case_id}/action", response_model=MaintenanceActionResponse)
async def record_action(
    case_id: uuid.UUID,
    body: RecordActionRequest,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[Principal, require_permission(Permission.MAINTENANCE_WRITE)],
) -> MaintenanceActionResponse:
    service = MaintenanceService(session)
    try:
        action = await service.record_action(
            tenant.id,
            case_id,
            action_type=body.action_type,
            notes=body.notes,
            recorded_by=body.recorded_by,
        )
    except MaintenanceCaseNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Maintenance case not found.") from exc
    except InvalidMaintenanceTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await _audit_case(
        session, tenant, principal, case_id, "MAINTENANCE_ACTION_RECORDED",
        reason=body.action_type.value,
    )
    return MaintenanceActionResponse.model_validate(action)


@router.post("/cases/{case_id}/complete", response_model=MaintenanceCaseResponse)
async def complete_case(
    case_id: uuid.UUID,
    body: CompleteCaseRequest,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[Principal, require_permission(Permission.MAINTENANCE_WRITE)],
) -> MaintenanceCaseResponse:
    """Requires an explicit technician feedback classification; runs a real, fresh
    post-action condition re-check and resolves the linked incident (Phase 17 brief
    §17.8-§17.12)."""
    service = MaintenanceService(session)
    try:
        case = await service.complete(
            tenant.id,
            case_id,
            classification=body.classification,
            confirmed_component=body.confirmed_component,
            confirmed_finding=body.confirmed_finding,
            notes=body.notes,
            recorded_by=body.recorded_by,
        )
    except MaintenanceCaseNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Maintenance case not found.") from exc
    except InvalidMaintenanceTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await _audit_case(
        session, tenant, principal, case_id, "MAINTENANCE_CASE_COMPLETED",
        reason=body.classification.value,
    )
    return MaintenanceCaseResponse.model_validate(case)


@router.post("/cases/{case_id}/cancel", response_model=MaintenanceCaseResponse)
async def cancel_case(
    case_id: uuid.UUID,
    body: CancelCaseRequest,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[Principal, require_permission(Permission.MAINTENANCE_WRITE)],
) -> MaintenanceCaseResponse:
    service = MaintenanceService(session)
    try:
        case = await service.cancel(tenant.id, case_id, reason=body.reason)
    except MaintenanceCaseNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Maintenance case not found.") from exc
    except InvalidMaintenanceTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await _audit_case(
        session, tenant, principal, case_id, "MAINTENANCE_CASE_CANCELLED", reason=body.reason
    )
    return MaintenanceCaseResponse.model_validate(case)


@router.post("/cases/{case_id}/cmms-draft", response_model=WorkOrderResponse)
async def create_cmms_draft(
    case_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[Principal, require_permission(Permission.CMMS_MANAGE)],
) -> WorkOrderResponse:
    """Draft-first only (Phase 20 brief §20.4) — never an external submission. A CMMS
    failure here never affects the underlying maintenance case (§20.6)."""
    service = CMMSService(session)
    try:
        record = await service.create_draft(tenant.id, case_id)
    except MaintenanceCaseNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Maintenance case not found.") from exc
    except CMMSUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    await AuditService(session).record(
        tenant.id,
        actor=AuditActor.from_principal(principal),
        action="CMMS_DRAFT_CREATED",
        entity_type="maintenance_case",
        entity_id=case_id,
        source="api.maintenance.cmms_draft",
        after_summary=f"Work order draft {record.external_reference}.",
    )
    return WorkOrderResponse(**dataclasses.asdict(record))
