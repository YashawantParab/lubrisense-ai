"""`ScenarioDefinition` — the configurable, YAML-loaded shape of a failure mode (Phase 4
brief §2, §19). Scenario definitions are data, not code: adding a new failure mode (or
retuning an existing one) means editing/adding a YAML file under
`simulator/config/scenarios/`, never adding a new `if scenario == ...` branch.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from simulator.scenarios.types import (
    VALID_TARGET_TYPES,
    ProgressionType,
    ScenarioTargetType,
    ScenarioType,
)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ProgressionSpec(_Frozen):
    type: ProgressionType
    onset_seconds: float = 3600.0
    period_s: float = 0.0
    duty_cycle: float = 0.5
    sigmoid_steepness: float = 6.0


class LifecycleSpec(_Frozen):
    """Severity thresholds (0.0-1.0) that promote a scenario instance's lifecycle state —
    see `simulator.scenarios.types.ScenarioLifecycleState`. `severe_threshold: null` means
    this scenario type never reaches `SEVERE` (Phase 4 brief §3: "Not every scenario needs
    all states")."""

    developing_threshold: float = 0.15
    severe_threshold: float | None = 0.6


class RecoverySpec(_Frozen):
    """Self-decay recovery (Phase 4 brief §23). `enabled=False` (the default for most
    catalog scenarios — a fault does not fix itself) means the instance holds at whatever
    severity its progression reaches and never reaches `COMPLETED` on its own. Reservoir
    recovery is handled separately by the standalone refill mechanism (§24,
    `simulator.scenarios.scheduler.AutoRefillPolicy`), not this spec."""

    enabled: bool = False
    hold_seconds: float = 0.0
    duration_seconds: float = 1800.0


class ScenarioDefinition(_Frozen):
    name: str
    scenario_type: ScenarioType
    target_type: ScenarioTargetType
    description: str
    default_start_seconds: float = 0.0
    default_severity_max: float = 1.0
    progression: ProgressionSpec
    lifecycle: LifecycleSpec = LifecycleSpec()
    recovery: RecoverySpec = RecoverySpec()
    #: Scenario-type-specific numeric magnitude coefficients (e.g.
    #: `max_restriction_factor` for GRADUAL_RESTRICTION) — read by
    #: `simulator.scenarios.effects` by convention per scenario type; see
    #: docs/SCENARIO_ENGINE.md §5 for the required keys per type. Kept as a typed
    #: `dict[str, float]` rather than one dataclass per scenario type so adding a new
    #: coefficient to one scenario type never touches the other nine's schema.
    effect_params: dict[str, float] = {}
    #: Free-form descriptive metadata only (author notes, catalog cross-reference) — never
    #: read by `effects.py`.
    metadata: dict[str, Any] = {}

    @model_validator(mode="after")
    def _validate_target_type(self) -> ScenarioDefinition:
        expected = VALID_TARGET_TYPES[self.scenario_type]
        if self.target_type != expected:
            raise ValueError(
                f"{self.scenario_type} must target {expected}, got {self.target_type} "
                f"(definition {self.name!r}) — see simulator.scenarios.types.VALID_TARGET_TYPES"
            )
        return self
