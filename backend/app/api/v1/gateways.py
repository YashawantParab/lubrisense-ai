"""Tenant-scoped gateway listing — a small, previously-missing read endpoint added
alongside Phase 30 commissioning (the guided workflow's "assign gateway" step needs a
way to list candidate gateways for a site)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session
from app.api.schemas.gateway import GatewayResponse
from app.domain.models import Gateway, Tenant
from app.repositories.gateway import GatewayRepository

router = APIRouter(prefix="/gateways", tags=["gateways"])


@router.get("", response_model=list[GatewayResponse])
async def list_gateways(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    site_id: uuid.UUID | None = None,
) -> list[GatewayResponse]:
    repo = GatewayRepository(session)
    filters = [Gateway.site_id == site_id] if site_id else []
    page = await repo.list(tenant.id, filters=filters)
    return [GatewayResponse.model_validate(g) for g in page.items]
