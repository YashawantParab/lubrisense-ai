"""Tenant-scoped Phase 20 CMMS read API. See docs/CMMS_INTEGRATION.md "Purpose"."""

from __future__ import annotations

import dataclasses
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session
from app.api.schemas.cmms import WorkOrderResponse
from app.cmms.observability import METRICS
from app.cmms.services.cmms_service import CMMSService, CMMSUnavailableError
from app.domain.models import Tenant

router = APIRouter(prefix="/cmms", tags=["cmms"])


@router.get("/metrics")
async def get_cmms_metrics() -> Response:
    return Response(content=METRICS.render_prometheus_text(), media_type="text/plain")


@router.get("/work-orders/{external_reference}", response_model=WorkOrderResponse)
async def get_work_order(
    external_reference: str,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkOrderResponse:
    service = CMMSService(session)
    try:
        record = await service.get_work_order(tenant.id, external_reference)
    except CMMSUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Work order not found.")
    return WorkOrderResponse(**dataclasses.asdict(record))
