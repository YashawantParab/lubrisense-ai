from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import OperationalStatus


class SiteCreateRequest(BaseModel):
    customer_account_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=50)
    country: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    timezone: str | None = Field(default=None, max_length=64)
    status: OperationalStatus = OperationalStatus.ACTIVE
    metadata: dict[str, Any] = Field(default_factory=dict)


class SiteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_account_id: uuid.UUID
    name: str
    code: str
    country: str | None
    city: str | None
    timezone: str | None
    status: OperationalStatus
    metadata_: dict[str, Any] = Field(serialization_alias="metadata")
    created_at: datetime
    updated_at: datetime
