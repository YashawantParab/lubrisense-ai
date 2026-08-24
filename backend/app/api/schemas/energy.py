"""Lubrication Efficiency Intelligence API contracts, Pass 1
(docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md, ADR-176). `EnergyAssessment` output is
energy EVIDENCE — an observed deviation from contextual expectation — never a
lubrication diagnosis; see the design doc's product-definition section for why."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EnergyAssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    machine_id: uuid.UUID
    power_sensor_id: uuid.UUID
    as_of_timestamp: datetime

    actual_power_kw: float | None
    expected_power_kw: float | None
    expected_lower_kw: float | None
    expected_upper_kw: float | None
    residual_kw: float | None
    residual_pct: float | None

    status: str
    data_quality_state: str
    baseline_source: str
    baseline_profile_id: uuid.UUID | None
    operating_state: str | None

    engine_version: str
    created_at: datetime
