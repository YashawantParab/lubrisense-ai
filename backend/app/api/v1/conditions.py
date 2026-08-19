"""Tenant-scoped Phase 13 condition-intelligence API. Output here is a SYNTHESIS of
Phase 7/9/11/12 evidence, never a diagnosis or maintenance decision — see
docs/CONDITION_INTELLIGENCE.md "Purpose"."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session
from app.api.schemas.condition_intelligence import ConditionAssessmentResponse
from app.condition_intelligence.observability import METRICS
from app.condition_intelligence.services.condition_engine import (
    ConditionEngine,
    ConditionEngineMachineNotFoundError,
)
from app.condition_intelligence.services.condition_query_service import (
    ConditionQueryMachineNotFoundError,
    ConditionQueryService,
)
from app.domain.models import Tenant

router = APIRouter(prefix="/conditions", tags=["conditions"])


@router.get("/machines/{machine_id}/latest", response_model=ConditionAssessmentResponse)
async def get_latest_condition(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ConditionAssessmentResponse:
    """Gathers current evidence and computes + persists a fresh `ConditionAssessment`."""
    engine = ConditionEngine(session)
    try:
        assessment = await engine.assess(tenant.id, machine_id)
    except ConditionEngineMachineNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found.") from exc
    return ConditionAssessmentResponse.model_validate(assessment)


@router.get("/machines/{machine_id}/history", response_model=list[ConditionAssessmentResponse])
async def get_condition_history(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    start: datetime | None = None,
    end: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[ConditionAssessmentResponse]:
    service = ConditionQueryService(session)
    try:
        results = await service.history(tenant.id, machine_id, start=start, end=end, limit=limit)
    except ConditionQueryMachineNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found.") from exc
    return [ConditionAssessmentResponse.model_validate(r) for r in results]


@router.get("/metrics")
async def get_condition_intelligence_metrics() -> Response:
    """Unscoped process metrics (mirrors `app.state_estimation`'s `/metrics` route — no
    periodic worker/health port exists for this package)."""
    return Response(content=METRICS.render_prometheus_text(), media_type="text/plain")
