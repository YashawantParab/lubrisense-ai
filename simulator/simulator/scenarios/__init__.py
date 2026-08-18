"""Scenario / failure-injection engine (Phase 4).

Public surface: `ScenarioDefinition`/`load_scenario_definition` (config), `create_instance`/
`ScenarioInstance` (runtime), `ScenarioScheduler` (per-run orchestration), `build_effects`/
`ScenarioEffects` (hidden-state adjustments the engine applies through the existing Phase 3
physics layer). See docs/SCENARIO_ENGINE.md for the architecture.

`HEALTHY` is the Phase 3 baseline label, kept for the no-scenario-active ground-truth case
(`docs/SYNTHETIC_DATA_MODEL.md` §2) — a healthy run is simply a `SimulationEngine` created
with zero scenario instances, not a special code path.
"""

from __future__ import annotations

from dataclasses import dataclass

from simulator.scenarios.definition import (
    LifecycleSpec,
    ProgressionSpec,
    RecoverySpec,
    ScenarioDefinition,
)
from simulator.scenarios.effects import ScenarioEffects, build_effects
from simulator.scenarios.instance import ScenarioInstance, create_instance
from simulator.scenarios.loader import (
    SCENARIO_CONFIG_VERSION,
    list_available_scenarios,
    load_scenario_definition,
)
from simulator.scenarios.scheduler import AutoRefillPolicy, ScenarioScheduler
from simulator.scenarios.targeting import ScenarioTargetError, resolve_target
from simulator.scenarios.types import (
    VALID_TARGET_TYPES,
    ProgressionType,
    ScenarioLifecycleState,
    ScenarioTargetType,
    ScenarioType,
)


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    description: str


HEALTHY = Scenario(
    name="NORMAL",
    description="All lubrication-system and machine-condition signals within configured "
    "baseline ranges — see docs/FAILURE_MODE_CATALOG.md §2.",
)

__all__ = [
    "HEALTHY",
    "SCENARIO_CONFIG_VERSION",
    "VALID_TARGET_TYPES",
    "AutoRefillPolicy",
    "LifecycleSpec",
    "ProgressionSpec",
    "ProgressionType",
    "RecoverySpec",
    "Scenario",
    "ScenarioDefinition",
    "ScenarioEffects",
    "ScenarioInstance",
    "ScenarioLifecycleState",
    "ScenarioScheduler",
    "ScenarioTargetError",
    "ScenarioTargetType",
    "ScenarioType",
    "build_effects",
    "create_instance",
    "list_available_scenarios",
    "load_scenario_definition",
    "resolve_target",
]
