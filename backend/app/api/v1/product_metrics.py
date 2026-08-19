"""Phase 22 product / North-Star metrics API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session, require_permission
from app.api.schemas.product_metrics import MetricResponse, ProductMetricsResponse
from app.auth.permissions import Permission
from app.domain.models import Tenant
from app.product_metrics.service import ProductMetricsService

router = APIRouter(prefix="/product-metrics", tags=["product-metrics"])


@router.get("", response_model=ProductMetricsResponse)
async def get_product_metrics(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _principal: Annotated[object, require_permission(Permission.METRICS_READ)],
) -> ProductMetricsResponse:
    service = ProductMetricsService(session)
    result = await service.all_metrics(tenant.id)
    return ProductMetricsResponse(
        north_star=MetricResponse.model_validate(result.north_star),
        supporting=[MetricResponse.model_validate(m) for m in result.supporting],
        generated_at=result.generated_at,
    )


@router.get("/north-star", response_model=MetricResponse)
async def get_north_star(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _principal: Annotated[object, require_permission(Permission.METRICS_READ)],
) -> MetricResponse:
    service = ProductMetricsService(session)
    result = await service.north_star(tenant.id)
    return MetricResponse.model_validate(result.metric)
