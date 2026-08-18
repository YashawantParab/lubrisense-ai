from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session
from app.api.schemas.hierarchy import HierarchyResponse
from app.domain.models import Tenant
from app.services.asset_hierarchy_service import AssetHierarchyService

router = APIRouter(tags=["hierarchy"])


@router.get("/hierarchy", response_model=HierarchyResponse)
async def get_hierarchy(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> HierarchyResponse:
    service = AssetHierarchyService(session)
    customers = await service.get_full_hierarchy(tenant.id)
    return HierarchyResponse.model_validate(
        {"customers": customers, "generated_at": datetime.now(UTC), "metadata": {}}
    )
