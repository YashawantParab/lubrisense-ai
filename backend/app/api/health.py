"""Liveness and readiness endpoints.

Unversioned by design: orchestrators (Docker healthchecks, Kubernetes probes, load
balancers) expect stable, well-known paths regardless of API version.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from app.api.deps import get_app_settings, get_database, get_redis_client
from app.core.config import Settings
from app.infrastructure.database import Database
from app.infrastructure.redis_client import RedisClient
from app.services.health_service import check_liveness, check_readiness

router = APIRouter(tags=["health"])


class LivenessResponse(BaseModel):
    status: str


class DependencyStatusResponse(BaseModel):
    name: str
    healthy: bool
    required: bool
    status: str


class ReadinessResponse(BaseModel):
    status: str
    dependencies: list[DependencyStatusResponse]


@router.get("/health", response_model=LivenessResponse)
async def get_health() -> LivenessResponse:
    """Process liveness. Always returns 200 if the process can handle requests at all."""
    check_liveness()
    return LivenessResponse(status="ok")


def _dependency_status_label(*, healthy: bool, required: bool) -> str:
    if healthy:
        return "healthy"
    return "unhealthy" if required else "unavailable_optional"


@router.get("/ready", response_model=ReadinessResponse)
async def get_readiness(
    response: Response,
    database: Database = Depends(get_database),
    redis_client: RedisClient = Depends(get_redis_client),
    settings: Settings = Depends(get_app_settings),
) -> ReadinessResponse:
    """Dependency readiness. Returns 503 if any *required* dependency is unreachable.

    An optional dependency (e.g. Redis in `hosted_demo` — docs/HOSTED_DEPLOYMENT.md §7/§13,
    where no Redis is provisioned and no reviewer-facing code path reads it) never fails
    overall readiness, but is still reported with its real health so it is never shown as
    falsely healthy.
    """
    result = await check_readiness(database, redis_client, settings)
    if not result.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if result.ready else "not_ready",
        dependencies=[
            DependencyStatusResponse(
                name=dep.name,
                healthy=dep.healthy,
                required=dep.required,
                status=_dependency_status_label(healthy=dep.healthy, required=dep.required),
            )
            for dep in result.dependencies
        ],
    )
