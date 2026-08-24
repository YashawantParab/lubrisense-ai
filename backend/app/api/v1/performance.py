"""Organization/site/area portfolio-performance API (Portfolio Intelligence Pass 1 —
post-roadmap capability extension, docs/PORTFOLIO_INTELLIGENCE.md, ADR-177). Read-only —
mirrors `app.api.v1.fleet`/`site_overview`/`customer_overview`'s own `Permission
.METRICS_READ`-gated, tenant-isolated convention exactly. Never triggers computation of
`EnergyAssessment`/`LubricationEnergyAttribution`/`EnergyOutcomeVerification`/
`CarbonImpactEstimate` — only reads what each capability's own service already
persisted."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session, require_permission
from app.api.schemas.portfolio import (
    AreaPerformanceResponse,
    AttentionAssetResponse,
    OrganizationPerformanceResponse,
    RecentOutcomeResponse,
    SitePerformanceResponse,
)
from app.auth.permissions import Permission
from app.domain.models import Tenant
from app.portfolio.services.portfolio_service import (
    PortfolioAreaNotFoundError,
    PortfolioService,
    PortfolioSiteNotFoundError,
)

router = APIRouter(prefix="/performance", tags=["performance"])


@router.get("/organization", response_model=OrganizationPerformanceResponse)
async def get_organization_performance(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _principal: Annotated[object, require_permission(Permission.METRICS_READ)],
) -> OrganizationPerformanceResponse:
    service = PortfolioService(session)
    summary = await service.organization_summary(tenant.id)
    return OrganizationPerformanceResponse.model_validate(summary)


@router.get("/sites", response_model=list[SitePerformanceResponse])
async def list_site_performance(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _principal: Annotated[object, require_permission(Permission.METRICS_READ)],
) -> list[SitePerformanceResponse]:
    service = PortfolioService(session)
    summaries = await service.site_summaries(tenant.id)
    return [SitePerformanceResponse.model_validate(s) for s in summaries]


@router.get("/sites/{site_id}", response_model=SitePerformanceResponse)
async def get_site_performance(
    site_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _principal: Annotated[object, require_permission(Permission.METRICS_READ)],
) -> SitePerformanceResponse:
    service = PortfolioService(session)
    try:
        summary = await service.site_summary(tenant.id, site_id)
    except PortfolioSiteNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found.") from exc
    return SitePerformanceResponse.model_validate(summary)


@router.get("/areas", response_model=list[AreaPerformanceResponse])
async def list_area_performance(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _principal: Annotated[object, require_permission(Permission.METRICS_READ)],
) -> list[AreaPerformanceResponse]:
    service = PortfolioService(session)
    summaries = await service.area_summaries(tenant.id)
    return [AreaPerformanceResponse.model_validate(s) for s in summaries]


@router.get("/areas/{area_key}", response_model=AreaPerformanceResponse)
async def get_area_performance(
    area_key: str,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _principal: Annotated[object, require_permission(Permission.METRICS_READ)],
) -> AreaPerformanceResponse:
    service = PortfolioService(session)
    try:
        summary = await service.area_summary(tenant.id, area_key)
    except PortfolioAreaNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Area not found.") from exc
    return AreaPerformanceResponse.model_validate(summary)


@router.get("/attention", response_model=list[AttentionAssetResponse])
async def get_attention_queue(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _principal: Annotated[object, require_permission(Permission.METRICS_READ)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[AttentionAssetResponse]:
    service = PortfolioService(session)
    assets = await service.attention_queue(tenant.id, limit=limit)
    return [AttentionAssetResponse.model_validate(a) for a in assets]


@router.get("/outcomes", response_model=list[RecentOutcomeResponse])
async def get_recent_outcomes(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _principal: Annotated[object, require_permission(Permission.METRICS_READ)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[RecentOutcomeResponse]:
    service = PortfolioService(session)
    outcomes = await service.recent_outcomes(tenant.id, limit=limit)
    return [RecentOutcomeResponse.model_validate(o) for o in outcomes]
