"""`BaselinePolicy` — versioned baseline configuration (Phase 8 brief §1/§9/§14/§20/§29/§41).

Fail-fast: every validator here raises before the baseline worker starts, mirroring
`app.data_quality.config.policy`'s own convention. Every threshold is a DEMO SYNTHETIC
BASELINE ASSUMPTION, not a validated production limit — see `demo_baseline_policy.yaml`'s
own disclaimer.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

DEFAULT_POLICY_PATH = Path(__file__).with_name("demo_baseline_policy.yaml")


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class EngineeringReferencePolicy(_Frozen):
    value_ranges: dict[str, tuple[float, float]] = Field(default_factory=dict)
    expected_unit: dict[str, str] = Field(default_factory=dict)

    @field_validator("value_ranges")
    @classmethod
    def _ranges_ordered(
        cls, value: dict[str, tuple[float, float]]
    ) -> dict[str, tuple[float, float]]:
        for measurement_type, (low, high) in value.items():
            if low >= high:
                raise ValueError(
                    f"value_ranges[{measurement_type!r}]: min must be < max (got {low}, {high})"
                )
        return value


class _DefaultByMeasurementType(_Frozen):
    default: float
    by_measurement_type: dict[str, float] = Field(default_factory=dict)

    def for_type(self, measurement_type: str) -> float:
        return self.by_measurement_type.get(measurement_type, self.default)


class MinSampleCountPolicy(_Frozen):
    default: int
    by_measurement_type: dict[str, int] = Field(default_factory=dict)

    def for_type(self, measurement_type: str) -> int:
        return self.by_measurement_type.get(measurement_type, self.default)


class StabilityGatePolicy(_Frozen):
    required_stable_cycles: int = 2
    candidate_divergence_mad_multiplier: float = 3.0

    @field_validator("required_stable_cycles")
    @classmethod
    def _positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("required_stable_cycles must be >= 1")
        return value


class DeviationPolicy(_Frozen):
    mild_multiplier: float = 2.0
    strong_multiplier: float = 4.0

    @field_validator("strong_multiplier")
    @classmethod
    def _ordered(cls, value: float, info: ValidationInfo) -> float:
        mild = info.data.get("mild_multiplier")
        if mild is not None and value <= mild:
            raise ValueError("strong_multiplier must be > mild_multiplier")
        return value


class BaselinePolicy(_Frozen):
    policy_version: str
    engineering_reference: EngineeringReferencePolicy = EngineeringReferencePolicy()
    contextual_measurement_types: list[str] = Field(default_factory=list)
    reservoir_trend_measurement_types: list[str] = Field(default_factory=list)
    context_dimensions: dict[str, list[str]] = Field(default_factory=dict)
    stable_operating_states: list[str] = Field(default_factory=list)
    cycle_phase_idle_threshold: dict[str, float] = Field(default_factory=dict)
    rolling_window_seconds: _DefaultByMeasurementType
    min_sample_count: MinSampleCountPolicy
    refresh_interval_seconds: _DefaultByMeasurementType
    stale_after_seconds: _DefaultByMeasurementType
    stability_gate: StabilityGatePolicy = StabilityGatePolicy()
    deviation: DeviationPolicy = DeviationPolicy()

    def value_range_for(self, measurement_type: str) -> tuple[float, float] | None:
        return self.engineering_reference.value_ranges.get(measurement_type)

    def expected_unit_for(self, measurement_type: str) -> str | None:
        return self.engineering_reference.expected_unit.get(measurement_type)

    def context_dimensions_for(self, measurement_type: str) -> list[str]:
        return self.context_dimensions.get(measurement_type, [])

    def uses_cycle_phase(self, measurement_type: str) -> bool:
        return "cycle_phase" in self.context_dimensions_for(measurement_type)

    def uses_operating_state(self, measurement_type: str) -> bool:
        return "operating_state" in self.context_dimensions_for(measurement_type)

    def is_contextual(self, measurement_type: str) -> bool:
        return measurement_type in self.contextual_measurement_types

    def is_reservoir_trend(self, measurement_type: str) -> bool:
        return measurement_type in self.reservoir_trend_measurement_types

    def rolling_window_seconds_for(self, measurement_type: str) -> float:
        return self.rolling_window_seconds.for_type(measurement_type)

    def min_sample_count_for(self, measurement_type: str) -> int:
        return self.min_sample_count.for_type(measurement_type)

    def refresh_interval_seconds_for(self, measurement_type: str) -> float:
        return self.refresh_interval_seconds.for_type(measurement_type)

    def stale_after_seconds_for(self, measurement_type: str) -> float:
        return self.stale_after_seconds.for_type(measurement_type)

    def cycle_phase_idle_threshold_for(self, measurement_type: str) -> float | None:
        return self.cycle_phase_idle_threshold.get(measurement_type)


_ENV_OVERRIDE = "BASELINE_POLICY_PATH"


def load_baseline_policy(path: Path | None = None) -> BaselinePolicy:
    """Load and validate the baseline policy. Raises `pydantic.ValidationError` on a
    malformed file rather than silently starting with unintended thresholds."""
    target = path or (Path(p) if (p := os.environ.get(_ENV_OVERRIDE)) else DEFAULT_POLICY_PATH)
    raw: dict[str, Any] = yaml.safe_load(target.read_text())
    return BaselinePolicy.model_validate(raw)
