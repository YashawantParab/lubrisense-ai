"""Tenant-scoped Phase 16 incident-management API. Correlates Decision/Condition evidence
into one coherent incident per evolving problem — never one row per evaluation cycle. See
docs/INCIDENT_MANAGEMENT.md "Purpose"."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session, require_permission
from app.api.schemas.incidents import (
    IncidentEventResponse,
    IncidentReasonRequest,
    IncidentResponse,
)
from app.audit.service import AuditActor, AuditService
from app.auth.models import Principal
from app.auth.permissions import Permission
from app.domain.enums import IncidentState
from app.domain.models import Tenant
from app.incidents.observability import METRICS
from app.incidents.services.incident_service import (
    IncidentNotFoundError,
    IncidentService,
    IncidentServiceMachineNotFoundError,
)
from app.incidents.services.lifecycle import InvalidIncidentTransitionError

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("", response_model=list[IncidentResponse])
async def list_incidents(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    machine_id: uuid.UUID | None = None,
    state: IncidentState | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[IncidentResponse]:
    service = IncidentService(session)
    incidents = await service.list_incidents(
        tenant.id, machine_id=machine_id, state=state, limit=limit
    )
    return [IncidentResponse.model_validate(i) for i in incidents]


@router.get("/metrics")
async def get_incident_metrics() -> Response:
    """Unscoped process metrics (mirrors Phase 12-15's own `/metrics` route — no periodic
    worker exists for this package). Registered before `/{incident_id}` so the literal
    path `metrics` is never mistaken for an incident id."""
    return Response(content=METRICS.render_prometheus_text(), media_type="text/plain")


@router.post("/machines/{machine_id}/evaluate", response_model=IncidentResponse | None)
async def evaluate_machine(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> IncidentResponse | None:
    """Triggers a fresh Phase 14 decision chain and correlates the result into an
    incident — creating one, updating an existing open one, resolving open incidents on
    recovery, or creating none at all (healthy/ambiguous/insufficient-evidence/
    data-quality-limited evidence never spins up an equipment incident)."""
    service = IncidentService(session)
    try:
        incident = await service.evaluate_machine(tenant.id, machine_id)
    except IncidentServiceMachineNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found.") from exc
    return IncidentResponse.model_validate(incident) if incident is not None else None


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    incident_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> IncidentResponse:
    service = IncidentService(session)
    try:
        incident = await service.get(tenant.id, incident_id)
    except IncidentNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found.") from exc
    return IncidentResponse.model_validate(incident)


@router.get("/{incident_id}/timeline", response_model=list[IncidentEventResponse])
async def get_incident_timeline(
    incident_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[IncidentEventResponse]:
    service = IncidentService(session)
    try:
        events = await service.timeline(tenant.id, incident_id)
    except IncidentNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found.") from exc
    return [IncidentEventResponse.model_validate(e) for e in events]


async def _transition_or_400(coro: object) -> IncidentResponse:
    try:
        incident = await coro  # type: ignore[misc]
    except IncidentNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found.") from exc
    except InvalidIncidentTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return IncidentResponse.model_validate(incident)


async def _audit_transition(
    session: AsyncSession,
    tenant: Tenant,
    principal: Principal,
    incident_id: uuid.UUID,
    action: str,
    reason: str | None = None,
) -> None:
    await AuditService(session).record(
        tenant.id,
        actor=AuditActor.from_principal(principal),
        action=action,
        entity_type="incident",
        entity_id=incident_id,
        source="api.incidents",
        reason=reason,
    )


@router.post("/{incident_id}/acknowledge", response_model=IncidentResponse)
async def acknowledge_incident(
    incident_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[Principal, require_permission(Permission.INCIDENT_MANAGE)],
) -> IncidentResponse:
    service = IncidentService(session)
    response = await _transition_or_400(service.acknowledge(tenant.id, incident_id))
    await _audit_transition(session, tenant, principal, incident_id, "INCIDENT_ACKNOWLEDGED")
    return response


@router.post("/{incident_id}/start-investigation", response_model=IncidentResponse)
async def start_investigation(
    incident_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[Principal, require_permission(Permission.INCIDENT_MANAGE)],
) -> IncidentResponse:
    service = IncidentService(session)
    response = await _transition_or_400(service.start_investigation(tenant.id, incident_id))
    await _audit_transition(
        session, tenant, principal, incident_id, "INCIDENT_INVESTIGATION_STARTED"
    )
    return response


@router.post("/{incident_id}/resolve", response_model=IncidentResponse)
async def resolve_incident(
    incident_id: uuid.UUID,
    body: IncidentReasonRequest,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[Principal, require_permission(Permission.INCIDENT_MANAGE)],
) -> IncidentResponse:
    service = IncidentService(session)
    response = await _transition_or_400(service.resolve(tenant.id, incident_id, reason=body.reason))
    await _audit_transition(
        session, tenant, principal, incident_id, "INCIDENT_RESOLVED", reason=body.reason
    )
    return response


@router.post("/{incident_id}/close", response_model=IncidentResponse)
async def close_incident(
    incident_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[Principal, require_permission(Permission.INCIDENT_MANAGE)],
) -> IncidentResponse:
    """Closing is always an explicit human action — never triggered automatically by
    recovery (Phase 16 brief §16.11)."""
    service = IncidentService(session)
    response = await _transition_or_400(service.close(tenant.id, incident_id))
    await _audit_transition(session, tenant, principal, incident_id, "INCIDENT_CLOSED")
    return response


@router.post("/{incident_id}/reopen", response_model=IncidentResponse)
async def reopen_incident(
    incident_id: uuid.UUID,
    body: IncidentReasonRequest,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[Principal, require_permission(Permission.INCIDENT_MANAGE)],
) -> IncidentResponse:
    service = IncidentService(session)
    response = await _transition_or_400(service.reopen(tenant.id, incident_id, reason=body.reason))
    await _audit_transition(
        session, tenant, principal, incident_id, "INCIDENT_REOPENED", reason=body.reason
    )
    return response
