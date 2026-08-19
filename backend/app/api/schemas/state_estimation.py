"""Phase 12 state-estimation API contracts. Output here is condition EVIDENCE (Phase 12
brief §16), never a diagnosis/decision — see docs/STATE_ESTIMATION.md "Purpose"."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StateEstimateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    machine_id: uuid.UUID
    component_id: uuid.UUID | None
    state_type: str
    as_of_timestamp: datetime
    state_value: float
    state_rate: float
    trend: str
    uncertainty: str
    covariance_summary: dict[str, float]
    estimator_id: str
    estimator_version: str
    config_version: str
    feature_set: str
    feature_set_version: str
    feature_vector_id: uuid.UUID
    dt_seconds: float
    prediction_only: bool
    observations_used: list[str]
    observations_missing: list[str]
    quality_summary: dict[str, object]
    created_at: datetime
