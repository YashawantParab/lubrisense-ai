from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import CommercialStatus, ServiceTier


class CustomerAccountCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=50)
    service_tier: ServiceTier
    industry: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, max_length=100)
    commercial_status: CommercialStatus = CommercialStatus.PROSPECT
    contract_start: date | None = None
    contract_end: date | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CustomerAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    service_tier: ServiceTier
    industry: str | None
    region: str | None
    country: str | None
    commercial_status: CommercialStatus
    contract_start: date | None
    contract_end: date | None
    metadata_: dict[str, Any] = Field(serialization_alias="metadata")
    created_at: datetime
    updated_at: datetime
