"""Response schemas for `app/api/v1/baselines.py` (Phase 8 brief §32)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.domain.enums import (
    BaselineMetricKind,
    BaselineSourceKind,
    BaselineState,
    BaselineStrategyType,
    DeviationClassification,
)


class BaselineProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sensor_id: uuid.UUID
    machine_id: uuid.UUID | None
    measurement_type: str
    strategy: BaselineStrategyType
    metric_kind: BaselineMetricKind
    context_key: str
    context: dict[str, Any]
    version: int
    state: BaselineState
    statistics: dict[str, Any] | None
    sample_count: int
    min_sample_required: int
    window_start: datetime | None
    window_end: datetime | None
    config_version: str
    quality_policy_version: str | None
    activated_at: datetime | None
    superseded_at: datetime | None
    invalidated_at: datetime | None
    invalidation_reason: str | None
    last_evaluated_at: datetime | None
    refresh_interval_seconds: float
    stale_after_seconds: float


class ReadinessResponse(BaseModel):
    label: str
    active_count: int
    building_count: int
    insufficient_data_count: int
    stale_count: int
    invalidated_count: int


class SensorBaselinesResponse(BaseModel):
    sensor_id: uuid.UUID
    readiness: ReadinessResponse
    profiles: list[BaselineProfileResponse]


class MachineBaselinesResponse(BaseModel):
    machine_id: uuid.UUID
    readiness: ReadinessResponse
    profiles: list[BaselineProfileResponse]


class DeviationResponse(BaseModel):
    classification: DeviationClassification
    standardized_distance: float | None
    quantile_position: float | None
    method: str


class CurrentBaselineResponse(BaseModel):
    sensor_id: uuid.UUID
    source: BaselineSourceKind
    profile: BaselineProfileResponse | None
    deviation: DeviationResponse | None


class TenantBaselineSummaryResponse(BaseModel):
    profiles_by_state: dict[str, int]
    total_profiles: int
