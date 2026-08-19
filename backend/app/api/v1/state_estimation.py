"""Tenant-scoped Phase 12 state-estimation API (Phase 12 brief §32). Output here is
condition EVIDENCE, never a diagnosis or maintenance decision — see
docs/STATE_ESTIMATION.md "Purpose"."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session
from app.api.schemas.state_estimation import StateEstimateResponse
from app.domain.models import Tenant
from app.features.config.policy import load_feature_policy
from app.state_estimation.config.policy import load_state_estimation_config
from app.state_estimation.observability import METRICS
from app.state_estimation.services.state_estimation_query_service import (
    StateEstimationQueryMachineNotFoundError,
    StateEstimationQueryService,
)
from app.state_estimation.services.state_estimation_service import (
    StateEstimationMachineNotFoundError,
    StateEstimationService,
)

router = APIRouter(prefix="/state-estimation", tags=["state-estimation"])
_POLICY = load_feature_policy()
_CONFIG = load_state_estimation_config()
_KNOWN_STATE_TYPES = tuple(_CONFIG.states)


@router.get("/machines/{machine_id}/latest", response_model=dict[str, StateEstimateResponse])
async def get_latest_state_estimates(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, StateEstimateResponse]:
    """Computes + persists the current estimate for every configured state type
    (`LUBRICATION_DELIVERY_STATE`, `BEARING_CONDITION_STATE`) from one shared Phase 10
    `STATE_ESTIMATION_V1` feature vector, and returns both."""
    service = StateEstimationService(session, _POLICY, _CONFIG)
    try:
        results = await service.compute_and_persist_latest(tenant.id, machine_id)
    except StateEstimationMachineNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found.") from exc
    return {
        state_type: StateEstimateResponse.model_validate(row) for state_type, row in results.items()
    }


@router.get("/machines/{machine_id}/history", response_model=list[StateEstimateResponse])
async def get_state_estimate_history(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    state_type: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[StateEstimateResponse]:
    if state_type is not None and state_type not in _KNOWN_STATE_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown state_type.")
    service = StateEstimationQueryService(session)
    try:
        results = await service.history(
            tenant.id, machine_id, state_type=state_type, start=start, end=end, limit=limit
        )
    except StateEstimationQueryMachineNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found.") from exc
    return [StateEstimateResponse.model_validate(r) for r in results]


@router.get("/metrics")
async def get_state_estimation_metrics() -> Response:
    """Unscoped process metrics (Phase 12 brief §34) — see
    `app.state_estimation.observability` for why this lives here rather than on a
    dedicated worker health port."""
    return Response(content=METRICS.render_prometheus_text(), media_type="text/plain")
