"""`StateEstimationConfig` — versioned Kalman-filter configuration (Phase 12 brief §14).

Fail-fast, same convention as `app.rules_engine.config.policy`/`app.baselines.config.
policy`: every validator raises before a caller ever gets a filter built from unintended
thresholds. Every threshold is a DEMO SYNTHETIC STATE-ESTIMATION ASSUMPTION — see
`state_estimation_v1.yaml`'s own disclaimer and docs/STATE_ESTIMATION.md.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

DEFAULT_POLICY_PATH = Path(__file__).with_name("state_estimation_v1.yaml")


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ObservationChannelConfig(_Frozen):
    feature_name: str
    mad_scale: float
    base_variance: float

    @field_validator("mad_scale", "base_variance")
    @classmethod
    def _positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("mad_scale and base_variance must be > 0")
        return value


class ProcessNoiseConfig(_Frozen):
    q_level: float
    q_rate: float

    @field_validator("q_level", "q_rate")
    @classmethod
    def _non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("process noise intensities must be >= 0")
        return value


class GapPolicy(_Frozen):
    max_dt_seconds: float
    min_dt_seconds: float
    max_prediction_only_gap_seconds: float

    @model_validator(mode="after")
    def _ordering(self) -> GapPolicy:
        if not 0 < self.min_dt_seconds < self.max_dt_seconds:
            raise ValueError("gap.min_dt_seconds must be > 0 and < gap.max_dt_seconds")
        if self.max_prediction_only_gap_seconds <= 0:
            raise ValueError("gap.max_prediction_only_gap_seconds must be > 0")
        return self


class UncertaintyThresholds(_Frozen):
    low_max_variance: float
    moderate_max_variance: float

    @model_validator(mode="after")
    def _ordering(self) -> UncertaintyThresholds:
        if not 0 < self.low_max_variance < self.moderate_max_variance:
            raise ValueError(
                "uncertainty.low_max_variance must be > 0 and < uncertainty.moderate_max_variance"
            )
        return self


class StateTypeConfig(_Frozen):
    channels: list[ObservationChannelConfig]
    caution_inflation_factor: float
    initial_level_variance: float
    initial_rate_variance: float
    process_noise: ProcessNoiseConfig
    level_bounds: tuple[float, float]
    rate_bound: float
    trend_rate_threshold: float
    rate_decay_tau_seconds: float
    minimum_observations: int = 1

    @field_validator("channels")
    @classmethod
    def _at_least_one_channel(
        cls, value: list[ObservationChannelConfig]
    ) -> list[ObservationChannelConfig]:
        if not value:
            raise ValueError("every state type needs at least one observation channel")
        return value

    @field_validator("caution_inflation_factor")
    @classmethod
    def _inflation_at_least_one(cls, value: float) -> float:
        if value < 1.0:
            raise ValueError("caution_inflation_factor must be >= 1.0 (never reduce trust)")
        return value

    @field_validator("level_bounds")
    @classmethod
    def _bounds_ordered(cls, value: tuple[float, float]) -> tuple[float, float]:
        low, high = value
        if not low < high:
            raise ValueError("level_bounds must be an ordered (low, high) pair")
        return value

    @field_validator("rate_bound", "trend_rate_threshold", "rate_decay_tau_seconds")
    @classmethod
    def _positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("rate_bound, trend_rate_threshold, rate_decay_tau_seconds must be > 0")
        return value

    @field_validator("minimum_observations")
    @classmethod
    def _at_least_one_required(cls, value: int) -> int:
        if value < 1:
            raise ValueError("minimum_observations must be >= 1")
        return value

    @model_validator(mode="after")
    def _threshold_within_bound(self) -> StateTypeConfig:
        if self.trend_rate_threshold >= self.rate_bound:
            raise ValueError("trend_rate_threshold must be < rate_bound")
        return self


class StateEstimationConfig(_Frozen):
    config_version: str
    estimator_version: str
    feature_set: str
    feature_set_version: str
    gap: GapPolicy
    uncertainty: UncertaintyThresholds
    states: dict[str, StateTypeConfig]

    @field_validator("states")
    @classmethod
    def _known_state_types(cls, value: dict[str, StateTypeConfig]) -> dict[str, StateTypeConfig]:
        # Deferred import avoids a config-module -> domain-enum import cycle at collection
        # time; StateType is the single source of truth for valid state-type identifiers.
        from app.domain.enums import StateType

        valid = {member.value for member in StateType}
        unknown = set(value) - valid
        if unknown:
            raise ValueError(f"unknown state type(s) in config: {sorted(unknown)}")
        if not value:
            raise ValueError("at least one state type must be configured")
        return value

    def state_config(self, state_type: str) -> StateTypeConfig:
        try:
            return self.states[state_type]
        except KeyError as exc:
            raise KeyError(f"no configuration for state type {state_type!r}") from exc


_ENV_OVERRIDE = "STATE_ESTIMATION_POLICY_PATH"


def load_state_estimation_config(path: Path | None = None) -> StateEstimationConfig:
    """Load and validate the state-estimation policy. Raises `pydantic.ValidationError` on
    a malformed file rather than silently starting with unintended thresholds."""
    target = path or (Path(p) if (p := os.environ.get(_ENV_OVERRIDE)) else DEFAULT_POLICY_PATH)
    raw: dict[str, Any] = yaml.safe_load(target.read_text())
    return StateEstimationConfig.model_validate(raw)
