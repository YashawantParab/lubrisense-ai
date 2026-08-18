from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import OperationalStatus


class PlantCreateRequest(BaseModel):
    site_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=50)
    plant_type: str | None = Field(default=None, max_length=100)
    status: OperationalStatus = OperationalStatus.ACTIVE
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    site_id: uuid.UUID
    name: str
    code: str
    plant_type: str | None
    status: OperationalStatus
    metadata_: dict[str, Any] = Field(serialization_alias="metadata")
    created_at: datetime
    updated_at: datetime
