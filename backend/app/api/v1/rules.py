"""Rule-finding read API (Phase 9 brief §32) — tenant-scoped via `get_current_tenant`,
same convention as `app/api/v1/data_quality.py`/`app/api/v1/baselines.py`."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session
from app.api.schemas.rules import (
    MachineFindingsResponse,
    RuleFindingResponse,
    TenantFindingSummaryResponse,
)
from app.domain.enums import RuleFindingSeverity, RuleFindingState, RuleFindingType
from app.domain.models import Tenant
from app.rules_engine.services.query_service import RuleFindingQueryService

router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("/findings", response_model=list[RuleFindingResponse])
async def list_findings(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    machine_id: uuid.UUID | None = None,
    finding_type: RuleFindingType | None = None,
    severity: RuleFindingSeverity | None = None,
    state: RuleFindingState | None = None,
    rule_id: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 200,
) -> list[RuleFindingResponse]:
    service = RuleFindingQueryService(session)
    findings = await service.list_findings(
        tenant.id,
        machine_id=machine_id,
        finding_type=finding_type,
        severity=severity,
        state=state,
        rule_id=rule_id,
        start=start,
        end=end,
        limit=limit,
    )
    return [RuleFindingResponse.model_validate(f) for f in findings]


@router.get("/machines/{machine_id}", response_model=MachineFindingsResponse)
async def get_machine_findings(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MachineFindingsResponse:
    service = RuleFindingQueryService(session)
    findings = await service.get_machine_findings(tenant.id, machine_id)
    return MachineFindingsResponse(
        machine_id=machine_id,
        findings=[RuleFindingResponse.model_validate(f) for f in findings],
    )


@router.get("/findings/{finding_id}", response_model=RuleFindingResponse)
async def get_finding(
    finding_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RuleFindingResponse:
    service = RuleFindingQueryService(session)
    finding = await service.get_finding(tenant.id, finding_id)
    return RuleFindingResponse.model_validate(finding)


@router.get("/summary", response_model=TenantFindingSummaryResponse)
async def get_summary(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TenantFindingSummaryResponse:
    service = RuleFindingQueryService(session)
    summary = await service.get_tenant_summary(tenant.id)
    return TenantFindingSummaryResponse.model_validate(summary)
