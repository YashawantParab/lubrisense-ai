"""Nested tree response for GET /api/v1/hierarchy — Customer -> Site -> Plant ->
ProductionLine -> Machine. Deliberately shallow (see AssetHierarchyService docstring)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import (
    CommercialStatus,
    Criticality,
    MachineStatus,
    MachineType,
    OperationalStatus,
    ServiceTier,
)


class HierarchyMachine(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    asset_code: str
    machine_type: MachineType
    criticality: Criticality
    status: MachineStatus


class HierarchyProductionLine(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    criticality: Criticality
    status: OperationalStatus
    machines: list[HierarchyMachine] = Field(default_factory=list)


class HierarchyPlant(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    status: OperationalStatus
    production_lines: list[HierarchyProductionLine] = Field(default_factory=list)


class HierarchySite(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    status: OperationalStatus
    plants: list[HierarchyPlant] = Field(default_factory=list)


class HierarchyCustomerAccount(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    service_tier: ServiceTier
    commercial_status: CommercialStatus
    sites: list[HierarchySite] = Field(default_factory=list)


class HierarchyResponse(BaseModel):
    customers: list[HierarchyCustomerAccount]
    generated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
