"""`QualityPolicy` — versioned data-quality configuration (Phase 7 brief §23).

Fail-fast: every validator here raises before the quality worker starts, rather than
silently running with unintended thresholds — mirrors `edge.config.models.EdgeConfig`'s
own fail-fast convention. Every threshold is a DEMO SYNTHETIC DATA QUALITY ASSUMPTION, not
a validated production limit — see `demo_quality_policy.yaml`'s own disclaimer.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.enums import Eligibility, QualityState

DEFAULT_POLICY_PATH = Path(__file__).with_name("demo_quality_policy.yaml")


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LatenessPolicy(_Frozen):
    late_threshold_seconds: float = 30.0
    very_late_threshold_seconds: float = 120.0

    @model_validator(mode="after")
    def _ordered(self) -> LatenessPolicy:
        if self.very_late_threshold_seconds <= self.late_threshold_seconds:
            raise ValueError(
                "very_late_threshold_seconds must be > late_threshold_seconds "
                f"(got late={self.late_threshold_seconds}, "
                f"very_late={self.very_late_threshold_seconds})"
            )
        return self


class StalenessPolicy(_Frozen):
    expected_interval_seconds: dict[str, float] = Field(default_factory=dict)
    stale_multiplier: float = 3.0

    @field_validator("stale_multiplier")
    @classmethod
    def _positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("stale_multiplier must be > 0")
        return value


class ClockPolicy(_Frozen):
    offset_warning_seconds: float = 5.0
    drift_window_minutes: float = 30.0
    drift_slope_warning_seconds_per_minute: float = 0.05


class ValidityPolicy(_Frozen):
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


class SensorDriftPolicy(_Frozen):
    window_minutes: float = 180.0
    min_samples: int = 20
    bias_fraction_of_range_warning: float = 0.05
    bias_fraction_of_range_error: float = 0.12

    @model_validator(mode="after")
    def _ordered(self) -> SensorDriftPolicy:
        if self.bias_fraction_of_range_error <= self.bias_fraction_of_range_warning:
            raise ValueError(
                "bias_fraction_of_range_error must be > bias_fraction_of_range_warning"
            )
        return self


class StuckSensorPolicy(_Frozen):
    window_minutes: float = 20.0
    min_samples: int = 8
    tolerant_types: list[str] = Field(default_factory=list)


class SpikePolicy(_Frozen):
    rate_of_change_fraction_of_range: dict[str, float] = Field(default_factory=dict)


class DuplicatePatternPolicy(_Frozen):
    lookback_minutes: float = 10.0


class EligibilityMappingEntry(_Frozen):
    quality_state: QualityState
    eligibility: Eligibility


class QualityPolicy(_Frozen):
    policy_version: str
    lateness: LatenessPolicy = LatenessPolicy()
    staleness: StalenessPolicy = StalenessPolicy()
    clock: ClockPolicy = ClockPolicy()
    validity: ValidityPolicy = ValidityPolicy()
    sensor_drift: SensorDriftPolicy = SensorDriftPolicy()
    stuck_sensor: StuckSensorPolicy = StuckSensorPolicy()
    spike: SpikePolicy = SpikePolicy()
    duplicate_pattern: DuplicatePatternPolicy = DuplicatePatternPolicy()
    window_evaluation_interval_seconds: float = 60.0
    # Keys are `IssueSeverity` values, or the literal "NONE" for the no-issues-found case.
    eligibility_mapping: dict[str, EligibilityMappingEntry] = Field(default_factory=dict)

    @field_validator("eligibility_mapping")
    @classmethod
    def _mapping_covers_every_severity(
        cls, value: dict[str, EligibilityMappingEntry]
    ) -> dict[str, EligibilityMappingEntry]:
        required = {"NONE", "INFO", "WARNING", "ERROR", "CRITICAL"}
        missing = required - value.keys()
        if missing:
            raise ValueError(f"eligibility_mapping is missing required key(s): {sorted(missing)}")
        return value

    def value_range_for(self, measurement_type: str) -> tuple[float, float] | None:
        return self.validity.value_ranges.get(measurement_type)

    def expected_unit_for(self, measurement_type: str) -> str | None:
        return self.validity.expected_unit.get(measurement_type)

    def expected_interval_seconds_for(self, measurement_type: str) -> float | None:
        return self.staleness.expected_interval_seconds.get(measurement_type)

    def rate_of_change_limit_for(self, measurement_type: str) -> float | None:
        """Absolute per-reading rate-of-change limit for one measurement type, derived
        from its configured range span (§21's "configurable per-sensor rate-of-change
        limits")."""
        fraction = self.spike.rate_of_change_fraction_of_range.get(measurement_type)
        value_range = self.value_range_for(measurement_type)
        if fraction is None or value_range is None:
            return None
        low, high = value_range
        return fraction * (high - low)


_ENV_OVERRIDE = "DATA_QUALITY_POLICY_PATH"


def load_quality_policy(path: Path | None = None) -> QualityPolicy:
    """Load and validate the quality policy. Raises `pydantic.ValidationError` on a
    malformed file rather than silently starting with unintended thresholds."""
    target = path or (Path(p) if (p := os.environ.get(_ENV_OVERRIDE)) else DEFAULT_POLICY_PATH)
    raw: dict[str, Any] = yaml.safe_load(target.read_text())
    return QualityPolicy.model_validate(raw)
