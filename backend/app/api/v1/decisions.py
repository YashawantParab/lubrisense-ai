"""Tenant-scoped Phase 14 decision-intelligence API. Every recommendation here requires
human review before any physical maintenance action — see docs/DECISION_INTELLIGENCE.md
"Human-review boundary"."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session
from app.api.schemas.decision_intelligence import DecisionAssessmentResponse
from app.decision_intelligence.observability import METRICS
from app.decision_intelligence.services.decision_engine import (
    DecisionEngine,
    DecisionEngineMachineNotFoundError,
)
from app.decision_intelligence.services.decision_query_service import (
    DecisionQueryMachineNotFoundError,
    DecisionQueryService,
)
from app.domain.models import Tenant

router = APIRouter(prefix="/decisions", tags=["decisions"])


@router.get("/machines/{machine_id}/latest", response_model=DecisionAssessmentResponse)
async def get_latest_decision(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DecisionAssessmentResponse:
    """Triggers a fresh condition assessment + forecast, then synthesizes and persists a
    decision (superseding the machine's previously-ACTIVE decision, never overwriting
    it)."""
    engine = DecisionEngine(session)
    try:
        bundle = await engine.decide_for_machine(tenant.id, machine_id)
    except DecisionEngineMachineNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found.") from exc
    return DecisionAssessmentResponse.model_validate(bundle.decision)


@router.get("/machines/{machine_id}/history", response_model=list[DecisionAssessmentResponse])
async def get_decision_history(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    start: datetime | None = None,
    end: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[DecisionAssessmentResponse]:
    service = DecisionQueryService(session)
    try:
        results = await service.history(tenant.id, machine_id, start=start, end=end, limit=limit)
    except DecisionQueryMachineNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found.") from exc
    return [DecisionAssessmentResponse.model_validate(r) for r in results]


@router.get("/metrics")
async def get_decision_intelligence_metrics() -> Response:
    """Unscoped process metrics (mirrors `app.state_estimation`'s `/metrics` route — no
    periodic worker/health port exists for this package). Also carries
    `intelligence_processing_errors`/`intelligence_processing_duration`, since
    `DecisionEngine` is the top of the chain that triggers Condition + Prognostics."""
    return Response(content=METRICS.render_prometheus_text(), media_type="text/plain")
