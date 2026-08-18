"""Versioned, model-agnostic feature contracts.

These contracts intentionally contain no simulator types or failure labels. They are used
unchanged by online computation and historical materialization.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

type FeatureValue = float | int | bool | str


class FeatureDataType(StrEnum):
    FLOAT = "FLOAT"
    INTEGER = "INTEGER"
    BOOLEAN = "BOOLEAN"
    STRING = "STRING"


class FeatureRegistryStatus(StrEnum):
    EXPERIMENTAL = "EXPERIMENTAL"
    VALIDATED = "VALIDATED"
    DEPRECATED = "DEPRECATED"


class FeatureGroup(StrEnum):
    CURRENT_STATE = "CURRENT_STATE"
    ROLLING_STATISTICAL = "ROLLING_STATISTICAL"
    BASELINE_DEVIATION = "BASELINE_DEVIATION"
    TREND_RATE = "TREND_RATE"
    CYCLE = "CYCLE"
    CROSS_SIGNAL = "CROSS_SIGNAL"
    TEMPORAL = "TEMPORAL"
    QUALITY = "QUALITY"
    CONTEXT = "CONTEXT"
    RULE_EVIDENCE = "RULE_EVIDENCE"


@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    version: str
    group: FeatureGroup
    data_type: FeatureDataType
    unit: str
    entity_scope: str
    source_measurements: tuple[str, ...]
    window_seconds: int | None
    aggregation: str
    context_requirements: tuple[str, ...]
    quality_requirement: str
    null_behavior: str
    description: str
    owner: str = "app.features"
    availability: str = "ON_DEMAND_AND_MATERIALIZED"
    status: FeatureRegistryStatus = FeatureRegistryStatus.VALIDATED
    feature_sets: tuple[str, ...] = ()


@dataclass(frozen=True)
class FeatureSetDefinition:
    name: str
    version: str
    intended_use: str
    feature_names: tuple[str, ...]


@dataclass(frozen=True)
class FeatureComputationResult:
    feature_vector_id: uuid.UUID
    feature_set: str
    feature_set_version: str
    tenant_id: uuid.UUID
    machine_id: uuid.UUID
    component_id: uuid.UUID | None
    as_of_timestamp: datetime
    feature_values: dict[str, FeatureValue]
    missing_features: tuple[str, ...]
    quality_summary: dict[str, object]
    source_window: dict[str, object]
    baseline_versions: dict[str, object]
    rule_versions: dict[str, object]
    feature_definition_versions: dict[str, str]
    created_at: datetime
    metrics: dict[str, int | float] = field(default_factory=dict)
