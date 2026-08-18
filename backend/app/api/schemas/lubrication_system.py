from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import CommissioningState, LubricationSystemType, OperationalStatus


class ReservoirResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lubrication_system_id: uuid.UUID
    name: str
    capacity_demo: float | None
    capacity_unit: str | None
    lubricant_type_demo: str | None
    status: OperationalStatus
    metadata_: dict[str, Any] = Field(serialization_alias="metadata")


class PumpResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lubrication_system_id: uuid.UUID
    name: str
    pump_type: str | None
    manufacturer: str | None
    model: str | None
    controller_reference: str | None
    status: OperationalStatus
    firmware_version_demo: str | None
    metadata_: dict[str, Any] = Field(serialization_alias="metadata")


class ControllerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lubrication_system_id: uuid.UUID
    name: str
    controller_type: str | None
    manufacturer: str | None
    model: str | None
    firmware_version: str | None
    configuration_version: str
    status: OperationalStatus
    metadata_: dict[str, Any] = Field(serialization_alias="metadata")


class DistributorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lubrication_system_id: uuid.UUID
    name: str
    type: str | None
    position: str | None
    status: OperationalStatus
    metadata_: dict[str, Any] = Field(serialization_alias="metadata")


class LubricationPointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    circuit_id: uuid.UUID
    bearing_id: uuid.UUID | None
    name: str
    code: str
    status: OperationalStatus
    metadata_: dict[str, Any] = Field(serialization_alias="metadata")


class CircuitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lubrication_system_id: uuid.UUID
    distributor_id: uuid.UUID | None
    name: str
    code: str
    status: OperationalStatus
    metadata_: dict[str, Any] = Field(serialization_alias="metadata")
    lubrication_points: list[LubricationPointResponse] = Field(default_factory=list)


class LubricationSystemSummaryResponse(BaseModel):
    """List-view shape: no nested equipment. Used by GET /lubrication-systems (plural) —
    that query does not eager-load reservoirs/pumps/etc, so accessing them here would
    either trigger a lazy load per row (N+1) or, under the async engine, raise
    `MissingGreenlet`. See GET /lubrication-systems/{id} (LubricationSystemResponse) for
    the full nested chain."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    machine_id: uuid.UUID
    name: str
    system_type: LubricationSystemType
    reservoir_id: uuid.UUID | None
    pump_id: uuid.UUID | None
    controller_id: uuid.UUID | None
    status: OperationalStatus
    commissioning_state: CommissioningState
    configuration_version: str
    metadata_: dict[str, Any] = Field(serialization_alias="metadata")
    created_at: datetime
    updated_at: datetime


class LubricationSystemResponse(LubricationSystemSummaryResponse):
    """Detail-view shape: full nested equipment chain. Only ever built from a query that
    eager-loaded these relationships (LubricationSystemRepository.get_with_equipment /
    MachineRepository.get_with_equipment)."""

    reservoirs: list[ReservoirResponse] = Field(default_factory=list)
    pumps: list[PumpResponse] = Field(default_factory=list)
    controllers: list[ControllerResponse] = Field(default_factory=list)
    distributors: list[DistributorResponse] = Field(default_factory=list)
    circuits: list[CircuitResponse] = Field(default_factory=list)
