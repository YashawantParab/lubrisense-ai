from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import Criticality, OperationalStatus


class ProductionLineCreateRequest(BaseModel):
    plant_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=1024)
    status: OperationalStatus = OperationalStatus.ACTIVE
    criticality: Criticality = Criticality.MEDIUM
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductionLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plant_id: uuid.UUID
    name: str
    code: str
    description: str | None
    status: OperationalStatus
    criticality: Criticality
    metadata_: dict[str, Any] = Field(serialization_alias="metadata")
    created_at: datetime
    updated_at: datetime
