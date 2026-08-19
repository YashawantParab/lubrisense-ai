from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.enums import OperationalStatus


class GatewayResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    site_id: uuid.UUID | None
    plant_id: uuid.UUID | None
    name: str
    gateway_code: str
    manufacturer_demo: str | None
    model_demo: str | None
    firmware_version: str | None
    status: OperationalStatus
    last_seen: datetime | None
    created_at: datetime
    updated_at: datetime
