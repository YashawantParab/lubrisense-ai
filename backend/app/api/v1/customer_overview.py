"""Phase 21 customer-level operational overview — read-only aggregates over persisted
platform data, gated by `Permission.METRICS_READ`."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session, require_permission
from app.api.schemas.customer_services import CustomerOverviewResponse
from app.auth.permissions import Permission
from app.customer_services.service import CustomerOverviewService
from app.domain.models import Tenant

router = APIRouter(prefix="/customers", tags=["customer-overview"])


@router.get("/{customer_account_id}/overview", response_model=CustomerOverviewResponse)
async def get_customer_overview(
    customer_account_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _principal: Annotated[object, require_permission(Permission.METRICS_READ)],
) -> CustomerOverviewResponse:
    service = CustomerOverviewService(session)
    overview = await service.customer_overview(tenant.id, customer_account_id)
    return CustomerOverviewResponse.model_validate(overview)
