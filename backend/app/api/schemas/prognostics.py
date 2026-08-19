"""Phase 15 prognostics API contracts. A forecast is a cautious "if the current trend
continues" extrapolation, never a certainty — see docs/PROGNOSTICS.md "Purpose"."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PrognosticAssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    machine_id: uuid.UUID
    component_id: uuid.UUID | None
    state_estimate_id: uuid.UUID
    state_type: str
    horizon: str
    status: str
    as_of_timestamp: datetime
    current_state: float
    trend: str
    predicted_state_at_horizon: float | None
    estimated_threshold_crossing_time: datetime | None
    uncertainty: str
    data_sufficient: bool
    limitations: list[str]
    engine_version: str
    config_version: str
    created_at: datetime
