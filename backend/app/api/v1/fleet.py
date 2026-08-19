"""Phase 21 tenant-wide fleet operational overview."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session, require_permission
from app.api.schemas.customer_services import FleetOverviewResponse
from app.auth.permissions import Permission
from app.customer_services.service import CustomerOverviewService
from app.domain.models import Tenant

router = APIRouter(prefix="/fleet", tags=["customer-overview"])


@router.get("/overview", response_model=FleetOverviewResponse)
async def get_fleet_overview(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _principal: Annotated[object, require_permission(Permission.METRICS_READ)],
) -> FleetOverviewResponse:
    service = CustomerOverviewService(session)
    overview = await service.fleet_overview(tenant.id)
    return FleetOverviewResponse.model_validate(overview)
