"""Phase 10 feature API contracts."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FeatureVectorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(validation_alias="id")
    feature_set: str
    feature_set_version: str
    tenant_id: uuid.UUID
    machine_id: uuid.UUID
    component_id: uuid.UUID | None
    as_of_timestamp: datetime
    feature_values: dict[str, object]
    missing_features: list[str]
    quality_summary: dict[str, object]
    source_window: dict[str, object]
    baseline_versions: dict[str, object]
    rule_versions: dict[str, object]
    feature_definition_versions: dict[str, object]
    created_at: datetime


class FeatureDefinitionResponse(BaseModel):
    feature_name: str
    feature_version: str
    group: str
    data_type: str
    unit: str
    entity_scope: str
    source_measurements: list[str]
    window_seconds: int | None
    aggregation: str
    context_requirements: list[str]
    quality_requirement: str
    null_behavior: str
    description: str
    owner: str
    availability: str
    status: str
    feature_sets: list[str]


class FeatureSetResponse(BaseModel):
    name: str
    version: str
    intended_use: str
    feature_count: int
    feature_names: list[str]
