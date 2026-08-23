"""Nested tree response for GET /api/v1/hierarchy — Customer -> Site -> Plant ->
ProductionLine -> Machine. Deliberately shallow (see AssetHierarchyService docstring)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import (
    CommercialStatus,
    Criticality,
    MachineStatus,
    MachineType,
    OperationalStatus,
    ServiceTier,
)


class HierarchyMachine(BaseModel):
    """`equipment_class`/`area` are product-presentation fields for the curated showcase
    fleet (industrial-asset-realism pass) — a specific equipment class (e.g. "Ball Mill")
    and synthetic process area (e.g. "Grinding"), read out of `Machine.metadata_` rather
    than mapped columns. `machine_type` (the coarse 6-value internal category) is kept
    unchanged for backend/simulator/historical-test compatibility — see CLAUDE.md's asset
    hierarchy — but primary customer-facing UI should prefer `equipment_class` when set,
    falling back to a humanized `machine_type` for every non-curated machine."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    asset_code: str
    machine_type: MachineType
    criticality: Criticality
    status: MachineStatus
    equipment_class: str | None = None
    area: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _extract_metadata_fields(cls, data: object) -> object:
        """`from_attributes=True` reads attributes straight off the ORM `Machine` object
        for every other field — `equipment_class`/`area` live inside its `metadata_` dict
        instead, which plain attribute-based extraction can't reach, so this pulls them
        out explicitly before the rest of validation runs. Already-dict input (e.g. from
        `model_validate({...})` in tests) passes through untouched."""
        if isinstance(data, dict):
            return data
        metadata = getattr(data, "metadata_", None) or {}
        return {
            "id": data.id,  # type: ignore[attr-defined]
            "name": data.name,  # type: ignore[attr-defined]
            "asset_code": data.asset_code,  # type: ignore[attr-defined]
            "machine_type": data.machine_type,  # type: ignore[attr-defined]
            "criticality": data.criticality,  # type: ignore[attr-defined]
            "status": data.status,  # type: ignore[attr-defined]
            "equipment_class": metadata.get("equipment_class"),
            "area": metadata.get("area"),
        }


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
