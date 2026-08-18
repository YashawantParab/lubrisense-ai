"""`RulesPolicy` — versioned rules-engine configuration (Phase 9 brief §21/§22).

Fail-fast, same convention as `app.data_quality.config.policy`/`app.baselines.config.
policy`: every validator raises before the worker starts rather than silently running with
unintended thresholds. Every threshold is a DEMO SYNTHETIC RULE ASSUMPTION — see
`demo_rules_policy.yaml`'s own disclaimer.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_POLICY_PATH = Path(__file__).with_name("demo_rules_policy.yaml")


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DebouncePolicy(_Frozen):
    default: int = 3
    by_finding_type: dict[str, int] = Field(default_factory=dict)

    @field_validator("default")
    @classmethod
    def _positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("debounce.required_stable_cycles.default must be >= 1")
        return value

    def required_stable_cycles_for(self, finding_type: str) -> int:
        return self.by_finding_type.get(finding_type, self.default)


class ReservoirPolicy(_Frozen):
    low_level_warning_percent: float = 20.0
    low_level_critical_percent: float = 8.0
    depletion_rate_abnormal_multiplier: float = 1.75


class CyclePolicy(_Frozen):
    pressure_build_slow_mad_multiplier: float = 2.0
    duration_above_baseline_mad_multiplier: float = 2.0
    completion_failure_rate_warning: float = 0.2
    completion_failure_rate_critical: float = 0.5


class CrossSignalPatternPolicy(_Frozen):
    requires: list[str] = Field(default_factory=list)
    supporting: list[str] = Field(default_factory=list)
    excludes: list[str] = Field(default_factory=list)
    minimum_distinct_signals: int | None = None


class CrossSignalPolicy(_Frozen):
    restriction: CrossSignalPatternPolicy = CrossSignalPatternPolicy()
    leakage: CrossSignalPatternPolicy = CrossSignalPatternPolicy()
    pump_degradation: CrossSignalPatternPolicy = CrossSignalPatternPolicy()
    lubrication_path_degradation: CrossSignalPatternPolicy = CrossSignalPatternPolicy()


class BearingPolicy(_Frozen):
    lubrication_signal_types: list[str] = Field(default_factory=list)


class SeverityPolicy(_Frozen):
    base_by_evidence_strength: dict[str, str] = Field(default_factory=dict)
    escalate_when_criticality_in: list[str] = Field(default_factory=list)
    escalate_when_evidence_strength_in: list[str] = Field(default_factory=list)

    @field_validator("base_by_evidence_strength")
    @classmethod
    def _covers_every_strength(cls, value: dict[str, str]) -> dict[str, str]:
        required = {"LOW", "MODERATE", "STRONG"}
        missing = required - value.keys()
        if missing:
            raise ValueError(
                f"severity.base_by_evidence_strength missing key(s): {sorted(missing)}"
            )
        return value


class DeviationPolicy(_Frozen):
    mild_multiplier: float = 2.0
    strong_multiplier: float = 4.0


class QualityGatingPolicy(_Frozen):
    caution_caps_evidence_strength_at: str = "MODERATE"
    minimum_eligible_sensor_fraction: float = 0.5

    @field_validator("minimum_eligible_sensor_fraction")
    @classmethod
    def _fraction(cls, value: float) -> float:
        if not (0.0 <= value <= 1.0):
            raise ValueError("minimum_eligible_sensor_fraction must be in [0, 1]")
        return value


class RulesPolicy(_Frozen):
    policy_version: str
    window_minutes: dict[str, Any] = Field(default_factory=dict)
    debounce: DebouncePolicy = DebouncePolicy()
    min_sample_count: int = 5
    reservoir: ReservoirPolicy = ReservoirPolicy()
    cycle: CyclePolicy = CyclePolicy()
    cross_signal: CrossSignalPolicy = CrossSignalPolicy()
    bearing: BearingPolicy = BearingPolicy()
    severity: SeverityPolicy = SeverityPolicy()
    quality: QualityGatingPolicy = QualityGatingPolicy()
    deviation: DeviationPolicy = DeviationPolicy()

    def window_minutes_for(self, category: str) -> float:
        by_category = self.window_minutes.get("by_category", {})
        default = self.window_minutes.get("default", 30.0)
        return float(by_category.get(category, default))

    def required_stable_cycles_for(self, finding_type: str) -> int:
        return self.debounce.required_stable_cycles_for(finding_type)


_ENV_OVERRIDE = "RULES_POLICY_PATH"


def load_rules_policy(path: Path | None = None) -> RulesPolicy:
    """Load and validate the rules policy. Raises `pydantic.ValidationError` on a malformed
    file rather than silently starting with unintended thresholds."""
    target = path or (Path(p) if (p := os.environ.get(_ENV_OVERRIDE)) else DEFAULT_POLICY_PATH)
    raw: dict[str, Any] = yaml.safe_load(target.read_text())
    return RulesPolicy.model_validate(raw)
