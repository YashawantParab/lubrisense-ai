"""Scenario engine enumerations and the target-type compatibility table (Phase 4 brief
§2, §17). See docs/SCENARIO_ENGINE.md for the full architecture.
"""

from __future__ import annotations

from enum import StrEnum


class ScenarioType(StrEnum):
    """The 10 injectable failure modes from docs/FAILURE_MODE_CATALOG.md (mode 1, Normal
    Operation, is simply the absence of any active scenario — there is no `NORMAL` member
    here; see `simulator.scenarios.HEALTHY` for that ground-truth label)."""

    GRADUAL_RESTRICTION = "GRADUAL_RESTRICTION"
    SUDDEN_BLOCKAGE = "SUDDEN_BLOCKAGE"
    LEAKAGE = "LEAKAGE"
    OVER_LUBRICATION = "OVER_LUBRICATION"
    LOW_RESERVOIR = "LOW_RESERVOIR"
    PUMP_DEGRADATION = "PUMP_DEGRADATION"
    SENSOR_DRIFT = "SENSOR_DRIFT"
    SENSOR_DROPOUT = "SENSOR_DROPOUT"
    NETWORK_FAILURE = "NETWORK_FAILURE"
    INDEPENDENT_BEARING_FAULT = "INDEPENDENT_BEARING_FAULT"


class ProgressionType(StrEnum):
    """Reusable severity-vs-time shapes (Phase 4 brief §4). `compute_severity` in
    `simulator.scenarios.progression` implements each; the resulting value is always in
    [0.0, 1.0] and is scaled by the scenario's own effect-specific magnitude."""

    STEP = "STEP"
    LINEAR = "LINEAR"
    EXPONENTIAL = "EXPONENTIAL"
    SIGMOID = "SIGMOID"
    INTERMITTENT = "INTERMITTENT"
    CYCLIC = "CYCLIC"


class ScenarioLifecycleState(StrEnum):
    """Not every scenario type visits every state (Phase 4 brief §3) — e.g. `SCHEDULED`
    only applies before `start_seconds`, and `SEVERE` only applies to scenario types whose
    definition configures a `severe_threshold`."""

    SCHEDULED = "SCHEDULED"
    ACTIVE = "ACTIVE"
    DEVELOPING = "DEVELOPING"
    SEVERE = "SEVERE"
    RECOVERING = "RECOVERING"
    COMPLETED = "COMPLETED"


class ScenarioTargetType(StrEnum):
    """What kind of Phase 2 entity a scenario instance resolves its target against
    (Phase 4 brief §17)."""

    MACHINE = "MACHINE"
    BEARING = "BEARING"
    LUBRICATION_SYSTEM = "LUBRICATION_SYSTEM"
    PUMP = "PUMP"
    RESERVOIR = "RESERVOIR"
    CIRCUIT = "CIRCUIT"
    SENSOR = "SENSOR"


#: Which target type each scenario type is allowed to act on — the compatibility table
#: `simulator.scenarios.targeting.resolve_target` enforces (Phase 4 brief §17: "Invalid or
#: incompatible target types must fail validation").
VALID_TARGET_TYPES: dict[ScenarioType, ScenarioTargetType] = {
    ScenarioType.GRADUAL_RESTRICTION: ScenarioTargetType.CIRCUIT,
    ScenarioType.SUDDEN_BLOCKAGE: ScenarioTargetType.CIRCUIT,
    ScenarioType.LEAKAGE: ScenarioTargetType.CIRCUIT,
    ScenarioType.OVER_LUBRICATION: ScenarioTargetType.LUBRICATION_SYSTEM,
    ScenarioType.LOW_RESERVOIR: ScenarioTargetType.RESERVOIR,
    ScenarioType.PUMP_DEGRADATION: ScenarioTargetType.PUMP,
    ScenarioType.SENSOR_DRIFT: ScenarioTargetType.SENSOR,
    ScenarioType.SENSOR_DROPOUT: ScenarioTargetType.SENSOR,
    ScenarioType.NETWORK_FAILURE: ScenarioTargetType.MACHINE,
    ScenarioType.INDEPENDENT_BEARING_FAULT: ScenarioTargetType.BEARING,
}
