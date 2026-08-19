"""System metadata endpoint.

Returns only safe, non-secret information: no connection strings, credentials, internal
hostnames, or stack traces belong here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from app.api.deps import get_app_settings
from app.core.config import Settings
from app.observability.http_metrics import HTTP_METRICS

router = APIRouter(prefix="/system", tags=["system"])


class SystemInfoResponse(BaseModel):
    application: str
    version: str
    environment: str


@router.get("/info", response_model=SystemInfoResponse)
async def get_system_info(settings: Settings = Depends(get_app_settings)) -> SystemInfoResponse:
    return SystemInfoResponse(
        application=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
    )


@router.get("/metrics")
async def get_system_metrics() -> Response:
    """Central cross-cutting HTTP metrics (Phase 26 brief §26.2) — request counts by
    status class, error count, mean latency, and auth failures. Package-specific
    pipeline/worker metrics remain at their own `/metrics` routes
    (`/incidents/metrics`, `/maintenance/cases/metrics`, `/knowledge/metrics`,
    `/agent/metrics`) — this endpoint is the HTTP-request-layer complement, not a
    replacement."""
    return Response(content=HTTP_METRICS.render_prometheus_text(), media_type="text/plain")
