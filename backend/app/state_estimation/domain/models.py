"""Versioned, config-agnostic state-estimation contracts (mirrors
`app.features.domain.models`/`ml_service.domain.feature_snapshot`'s role for their own
layers). Contains no simulator types and no ORM — `app.domain.models.StateEstimate` is the
persistence-layer mapping of `StateEstimateResult` below, kept as a separate dataclass so
the estimator's own math/services never depend on SQLAlchemy.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class PriorEstimate:
    """The previous posterior a filter run continues from (Phase 12 brief §18) — absent for
    a machine/state_type/estimator_version with no prior history, in which case the
    estimator initializes from its own configured `initial_level_variance`/
    `initial_rate_variance` instead of predicting from this."""

    as_of_timestamp: datetime
    level: float
    rate: float
    p00: float
    p01: float
    p11: float


@dataclass(frozen=True, slots=True)
class ChannelObservation:
    """One observation channel's contribution at one tick — kept for
    `observations_used`/diagnostics, not persisted verbatim."""

    feature_name: str
    raw_value: float
    normalized_evidence: float
    variance: float
    quality_inflated: bool


@dataclass(frozen=True, slots=True)
class StateEstimateResult:
    """One filter step's complete output (Phase 12 brief §16) — the state-estimation
    analogue of `app.features.domain.models.FeatureComputationResult` /
    `ml_service.domain.inference.*Result`."""

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
    observations_used: tuple[str, ...]
    observations_missing: tuple[str, ...]
    quality_summary: dict[str, object]

    def to_prior(self) -> PriorEstimate:
        """This result, viewed as the `PriorEstimate` input for the *next* step."""
        return PriorEstimate(
            as_of_timestamp=self.as_of_timestamp,
            level=self.state_value,
            rate=self.state_rate,
            p00=self.covariance_summary["p00"],
            p01=self.covariance_summary["p01"],
            p11=self.covariance_summary["p11"],
        )
