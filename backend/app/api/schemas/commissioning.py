from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.enums import CapabilityLevel, CommissioningStatus, SensorType


class StartCommissioningRequest(BaseModel):
    production_line_id: uuid.UUID
    name: str
    asset_code: str
    machine_type: str


class AddSensorRequest(BaseModel):
    sensor_type: SensorType
    sensor_code: str
    name: str
    unit: str | None = None


class AssignGatewayRequest(BaseModel):
    gateway_id: uuid.UUID


class ValidationIssueResponse(BaseModel):
    code: str
    message: str
    blocking: bool


class CommissioningSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    machine_id: uuid.UUID
    gateway_id: uuid.UUID | None
    status: CommissioningStatus
    capability_level: CapabilityLevel
    validation_issues: list[ValidationIssueResponse]
    steps_completed: list[str]
    notes: str | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
