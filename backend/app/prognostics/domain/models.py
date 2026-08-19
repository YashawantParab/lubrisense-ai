"""Label-free prognostics contracts."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class StateEstimateSnapshot:
    """The minimal slice of a Phase 12 `StateEstimate` row the forecaster needs — decouples
    `app.prognostics` from the ORM directly."""

    id: uuid.UUID
    state_type: str
    as_of_timestamp: datetime
    level: float
    rate: float
    trend: str
    uncertainty: str
    prediction_only: bool


@dataclass(frozen=True, slots=True)
class ForecastResult:
    status: str  # "OK" | "NO_RELIABLE_FORECAST"
    predicted_state_at_horizon: float | None
    threshold_crossing_seconds: float | None
    uncertainty: str
    data_sufficient: bool
    limitations: tuple[str, ...]
