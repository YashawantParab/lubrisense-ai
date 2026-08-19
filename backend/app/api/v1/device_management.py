"""Tenant-scoped Phase 31 device/configuration governance API — visibility only, no
OTA/remote-configuration capability. See docs/DEVICE_CONFIGURATION.md "Purpose"."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session
from app.api.schemas.device_management import (
    ConfigurationChangeResponse,
    ConfigurationSnapshotResponse,
)
from app.device_management.service import DeviceConfigurationService
from app.domain.models import Tenant

router = APIRouter(prefix="/device-management", tags=["device-management"])


@router.get(
    "/machines/{machine_id}/devices", response_model=list[ConfigurationSnapshotResponse]
)
async def get_machine_devices(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[ConfigurationSnapshotResponse]:
    service = DeviceConfigurationService(session)
    snapshots = await service.get_machine_devices(tenant.id, machine_id)
    return [ConfigurationSnapshotResponse.model_validate(s) for s in snapshots]


@router.get(
    "/machines/{machine_id}/changes", response_model=list[ConfigurationChangeResponse]
)
async def get_machine_changes(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[ConfigurationChangeResponse]:
    service = DeviceConfigurationService(session)
    changes = await service.list_changes(tenant.id, machine_id)
    return [ConfigurationChangeResponse.model_validate(c) for c in changes]
