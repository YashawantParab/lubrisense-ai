"""`ConditionIntelligencePolicy` — versioned evidence-synthesis configuration (Phase 13
brief). Fail-fast, same convention as every prior phase's config module. Every mapping is
a DEMO SYNTHETIC CONDITION-INTELLIGENCE ASSUMPTION — see `condition_intelligence_v1.yaml`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, field_validator

DEFAULT_POLICY_PATH = Path(__file__).with_name("condition_intelligence_v1.yaml")


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ConfidencePolicy(_Frozen):
    high_requires_corroboration: bool
    moderate_min_supporting_sources: int


class RuleFindingMapEntry(_Frozen):
    condition: str
    strength: str


class SeverityOverride(_Frozen):
    finding_type: str
    when_severity: str
    condition: str


class StateEstimatePolicy(_Frozen):
    minimum_meaningful_level: float

    @field_validator("minimum_meaningful_level")
    @classmethod
    def _bounded(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("state_estimate.minimum_meaningful_level must be in [0, 1]")
        return value


class QualityGatePolicy(_Frozen):
    unusable_fraction_threshold: float

    @field_validator("unusable_fraction_threshold")
    @classmethod
    def _bounded(cls, value: float) -> float:
        if not 0.0 < value <= 1.0:
            raise ValueError("quality_gate.unusable_fraction_threshold must be in (0, 1]")
        return value


class LifecyclePolicy(_Frozen):
    developing_after_consecutive: int
    persistent_after_consecutive: int

    @field_validator("developing_after_consecutive", "persistent_after_consecutive")
    @classmethod
    def _positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("lifecycle thresholds must be >= 1")
        return value


class ConditionIntelligencePolicy(_Frozen):
    policy_version: str
    engine_version: str
    confidence: ConfidencePolicy
    rule_finding_map: dict[str, RuleFindingMapEntry]
    severity_override: SeverityOverride
    ml_classification_map: dict[str, str]
    state_estimate: StateEstimatePolicy
    quality_gate: QualityGatePolicy
    severity_rank: dict[str, int]
    default_severity: dict[str, str]
    lifecycle: LifecyclePolicy

    def rank(self, severity: str) -> int:
        return self.severity_rank[severity]


_ENV_OVERRIDE = "CONDITION_INTELLIGENCE_POLICY_PATH"


def load_condition_intelligence_policy(path: Path | None = None) -> ConditionIntelligencePolicy:
    """Load and validate the condition-intelligence policy. Raises `pydantic.
    ValidationError` on a malformed file rather than silently starting with unintended
    evidence-mapping rules."""
    target = path or (Path(p) if (p := os.environ.get(_ENV_OVERRIDE)) else DEFAULT_POLICY_PATH)
    raw: dict[str, Any] = yaml.safe_load(target.read_text())
    return ConditionIntelligencePolicy.model_validate(raw)
