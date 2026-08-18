from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.bearing import BearingResponse
from app.api.schemas.lubrication_system import LubricationSystemResponse
from app.api.schemas.sensor import SensorResponse
from app.domain.enums import Criticality, MachineStatus, MachineType


class MachineCreateRequest(BaseModel):
    production_line_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)
    asset_code: str = Field(min_length=1, max_length=50)
    machine_type: MachineType
    manufacturer: str | None = Field(default=None, max_length=150)
    model: str | None = Field(default=None, max_length=150)
    serial_number_demo: str | None = Field(default=None, max_length=100)
    installation_date: date | None = None
    criticality: Criticality = Criticality.MEDIUM
    status: MachineStatus = MachineStatus.REGISTERED
    operating_profile: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MachineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    production_line_id: uuid.UUID
    name: str
    asset_code: str
    machine_type: MachineType
    manufacturer: str | None
    model: str | None
    serial_number_demo: str | None
    installation_date: date | None
    criticality: Criticality
    operating_profile: dict[str, Any]
    status: MachineStatus
    metadata_: dict[str, Any] = Field(serialization_alias="metadata")
    created_at: datetime
    updated_at: datetime


class MachineHierarchyResponse(BaseModel):
    """Response for GET /api/v1/machines/{id}/hierarchy — machine + bearings + full
    lubrication-system chain + every sensor attached anywhere in that tree."""

    machine: MachineResponse
    bearings: list[BearingResponse]
    lubrication_systems: list[LubricationSystemResponse]
    sensors: list[SensorResponse]
