"""System metadata endpoint.

Returns only safe, non-secret information: no connection strings, credentials, internal
hostnames, or stack traces belong here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_app_settings
from app.core.config import Settings

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
