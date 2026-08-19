"""Tenant-scoped Phase 15 prognostics API. Output here is a cautious, explainable
extrapolation of Phase 12 evidence, never a certainty — see docs/PROGNOSTICS.md
"Purpose"."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session
from app.api.schemas.prognostics import PrognosticAssessmentResponse
from app.domain.models import Tenant
from app.prognostics.observability import METRICS
from app.prognostics.services.prognostic_engine import (
    PrognosticEngine,
    PrognosticEngineMachineNotFoundError,
)
from app.prognostics.services.prognostic_query_service import (
    PrognosticQueryMachineNotFoundError,
    PrognosticQueryService,
)

router = APIRouter(prefix="/prognostics", tags=["prognostics"])


@router.get("/machines/{machine_id}/latest", response_model=list[PrognosticAssessmentResponse])
async def get_latest_prognostics(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[PrognosticAssessmentResponse]:
    """Computes + persists a fresh forecast for every configured `(state_type, horizon)`
    pair from the current Phase 12 state estimate."""
    engine = PrognosticEngine(session)
    try:
        results = await engine.forecast_machine(tenant.id, machine_id)
    except PrognosticEngineMachineNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found.") from exc
    return [PrognosticAssessmentResponse.model_validate(r) for r in results]


@router.get("/machines/{machine_id}/history", response_model=list[PrognosticAssessmentResponse])
async def get_prognostic_history(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    state_type: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[PrognosticAssessmentResponse]:
    service = PrognosticQueryService(session)
    try:
        results = await service.history(
            tenant.id, machine_id, state_type=state_type, start=start, end=end, limit=limit
        )
    except PrognosticQueryMachineNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found.") from exc
    return [PrognosticAssessmentResponse.model_validate(r) for r in results]


@router.get("/metrics")
async def get_prognostics_metrics() -> Response:
    """Unscoped process metrics (mirrors `app.state_estimation`'s `/metrics` route — no
    periodic worker/health port exists for this package)."""
    return Response(content=METRICS.render_prometheus_text(), media_type="text/plain")
