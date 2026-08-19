from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.domain.enums import CompatibilityStatus, DeviceType


class ConfigurationSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    machine_id: uuid.UUID
    device_type: DeviceType
    device_id: uuid.UUID
    firmware_version: str | None
    config: dict[str, Any]
    compatibility_status: CompatibilityStatus
    is_current: bool
    captured_at: datetime


class ConfigurationChangeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    machine_id: uuid.UUID
    device_type: DeviceType
    device_id: uuid.UUID
    previous_snapshot_id: uuid.UUID | None
    new_snapshot_id: uuid.UUID
    changed_by: str
    reason: str | None
    source: str
    baseline_review_required: bool
    occurred_at: datetime
