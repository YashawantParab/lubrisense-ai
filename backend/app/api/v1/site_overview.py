"""Phase 21 site-level operational overview."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session, require_permission
from app.api.schemas.customer_services import SiteOverviewResponse
from app.auth.permissions import Permission
from app.customer_services.service import CustomerOverviewService
from app.domain.models import Tenant

router = APIRouter(prefix="/sites", tags=["customer-overview"])


@router.get("/{site_id}/overview", response_model=SiteOverviewResponse)
async def get_site_overview(
    site_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _principal: Annotated[object, require_permission(Permission.METRICS_READ)],
) -> SiteOverviewResponse:
    service = CustomerOverviewService(session)
    overview = await service.site_overview(tenant.id, site_id)
    return SiteOverviewResponse.model_validate(overview)
