from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import Criticality, OperationalStatus


class BearingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    machine_id: uuid.UUID
    name: str
    position: str
    bearing_type: str | None
    manufacturer: str | None
    model: str | None
    criticality: Criticality
    installation_date: date | None
    status: OperationalStatus
    metadata_: dict[str, Any] = Field(serialization_alias="metadata")
    created_at: datetime
    updated_at: datetime
