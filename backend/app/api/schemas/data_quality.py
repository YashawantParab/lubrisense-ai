"""Response schemas for `app/api/v1/data_quality.py` (Phase 7 brief §32-§34).

Deliberately exposes only `TRUSTED`/`USABLE_WITH_CAUTION`/`UNUSABLE` — never
`HEALTHY`/`FAILED` (brief §33's explicit naming instruction for the frontend and, by
extension, its own API contract).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import (
    ClockStatus,
    Eligibility,
    IssueSeverity,
    IssueStatus,
    QualityDimension,
    QualityIssueType,
    QualityState,
    StalenessStatus,
)


class SensorQualityStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sensor_id: uuid.UUID
    machine_id: uuid.UUID | None
    quality_state: QualityState
    eligibility: Eligibility
    last_good_reading_at: datetime | None
    last_good_reading_value: float | None
    last_observed_at: datetime | None
    last_observed_value: float | None
    last_observed_quality: str | None
    staleness_status: StalenessStatus
    clock_status: ClockStatus
    active_issue_count: int
    firmware_version: str | None
    controller_version: str | None
    policy_version: str | None
    updated_at: datetime


class QualityIssueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sensor_id: uuid.UUID
    machine_id: uuid.UUID | None
    dimension: QualityDimension
    issue_type: QualityIssueType
    severity: IssueSeverity
    status: IssueStatus
    message: str
    evidence: dict[str, object]
    first_seen: datetime
    last_seen: datetime
    resolved_at: datetime | None
    rule_id: str
    rule_version: str
    policy_version: str


class SensorQualityDetailResponse(BaseModel):
    sensor_id: uuid.UUID
    state: SensorQualityStateResponse | None
    active_issues: list[QualityIssueResponse]


class MachineQualitySummaryResponse(BaseModel):
    machine_id: uuid.UUID
    sensors: list[SensorQualityStateResponse]
    active_issues: list[QualityIssueResponse]


class TenantQualitySummaryResponse(BaseModel):
    sensors_by_quality_state: dict[str, int]
    active_issues_by_severity: dict[str, int]
    total_sensors_tracked: int
    total_active_issues: int = Field(description="Sum of active_issues_by_severity's values")
