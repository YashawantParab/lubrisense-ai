"""`DecisionIntelligencePolicy` — versioned decision-priority/action configuration (Phase
14 brief). Fail-fast, same convention as every prior phase's config module. Every
mapping/window/expiry is a DEMO SYNTHETIC DECISION ASSUMPTION — see
`decision_intelligence_v1.yaml`."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, field_validator

DEFAULT_POLICY_PATH = Path(__file__).with_name("decision_intelligence_v1.yaml")

_PRIORITY_TIERS = ("MONITOR", "PLANNED", "HIGH", "URGENT")


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TierAdjustments(_Frozen):
    persistent_lifecycle: int
    criticality_high_or_critical: int
    imminent_threshold_crossing: int


class DecisionIntelligencePolicy(_Frozen):
    policy_version: str
    engine_version: str
    severity_priority_tier: dict[str, int]
    tier_adjustments: TierAdjustments
    imminent_crossing_seconds: float
    condition_action_map: dict[str, str]
    non_physical_actions: list[str]
    priority_window_map: dict[str, str]
    risk_language: dict[str, str]
    expiry_seconds_by_priority: dict[str, float]

    @field_validator("severity_priority_tier")
    @classmethod
    def _tiers_in_range(cls, value: dict[str, int]) -> dict[str, int]:
        if any(not 0 <= v <= 3 for v in value.values()):
            raise ValueError("severity_priority_tier values must be in [0, 3]")
        return value

    @field_validator("priority_window_map", "expiry_seconds_by_priority")
    @classmethod
    def _known_priorities(cls, value: dict[str, Any]) -> dict[str, Any]:
        if set(value) != set(_PRIORITY_TIERS):
            raise ValueError(f"must define exactly the priority tiers {_PRIORITY_TIERS}")
        return value

    def priority_for_tier(self, tier: int) -> str:
        return _PRIORITY_TIERS[max(0, min(tier, 3))]

    def tier_for_priority(self, priority: str) -> int:
        return _PRIORITY_TIERS.index(priority)


_ENV_OVERRIDE = "DECISION_INTELLIGENCE_POLICY_PATH"


def load_decision_intelligence_policy(path: Path | None = None) -> DecisionIntelligencePolicy:
    """Load and validate the decision-intelligence policy. Raises `pydantic.
    ValidationError` on a malformed file rather than silently starting with unintended
    priority/action mappings."""
    target = path or (Path(p) if (p := os.environ.get(_ENV_OVERRIDE)) else DEFAULT_POLICY_PATH)
    raw: dict[str, Any] = yaml.safe_load(target.read_text())
    return DecisionIntelligencePolicy.model_validate(raw)
