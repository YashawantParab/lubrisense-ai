"""Liveness and readiness endpoints.

Unversioned by design: orchestrators (Docker healthchecks, Kubernetes probes, load
balancers) expect stable, well-known paths regardless of API version.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from app.api.deps import get_database, get_redis_client
from app.infrastructure.database import Database
from app.infrastructure.redis_client import RedisClient
from app.services.health_service import check_liveness, check_readiness

router = APIRouter(tags=["health"])


class LivenessResponse(BaseModel):
    status: str


class DependencyStatusResponse(BaseModel):
    name: str
    healthy: bool


class ReadinessResponse(BaseModel):
    status: str
    dependencies: list[DependencyStatusResponse]


@router.get("/health", response_model=LivenessResponse)
async def get_health() -> LivenessResponse:
    """Process liveness. Always returns 200 if the process can handle requests at all."""
    check_liveness()
    return LivenessResponse(status="ok")


@router.get("/ready", response_model=ReadinessResponse)
async def get_readiness(
    response: Response,
    database: Database = Depends(get_database),
    redis_client: RedisClient = Depends(get_redis_client),
) -> ReadinessResponse:
    """Dependency readiness. Returns 503 if any critical dependency is unreachable."""
    result = await check_readiness(database, redis_client)
    if not result.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if result.ready else "not_ready",
        dependencies=[
            DependencyStatusResponse(name=dep.name, healthy=dep.healthy)
            for dep in result.dependencies
        ],
    )
