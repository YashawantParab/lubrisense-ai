"""Translate active `ScenarioInstance` severities into hidden-physical-state adjustments
(Phase 4 brief §1: "scenario modifies hidden physical parameters -> physics model evolves ->
sensors observe resulting physical state" — never `if scenario == X: sensor_value = Y`).

`build_effects` aggregates every active instance into one `ScenarioEffects` snapshot per
tick; `simulator.engine.simulation_engine.SimulationEngine` applies that snapshot by
passing its values into the existing Phase 3 physics functions (`step_natural_variation`,
`step_efficiency`, `step_health`, the cycle controller, ...) as additional inputs — the
physics functions themselves stay ignorant of "scenarios" as a concept; they just receive a
slightly different offset/target than they would on a healthy run. See
docs/SCENARIO_ENGINE.md §3-§6 for the full mapping and the multi-fault precedence rules.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from simulator.config.loader import EngineeringConfig
from simulator.domain.topology import MachineTopology
from simulator.scenarios.instance import ScenarioInstance
from simulator.scenarios.types import ScenarioType


@dataclass(slots=True)
class ScenarioEffects:
    """One tick's worth of aggregated scenario-driven hidden-state adjustments. All maps
    are keyed by the real Phase 2 entity id the effect applies to."""

    circuit_restriction_offset: dict[uuid.UUID, float] = field(default_factory=dict)
    circuit_leakage_offset: dict[uuid.UUID, float] = field(default_factory=dict)
    pump_efficiency_offset: dict[uuid.UUID, float] = field(default_factory=dict)
    volume_multiplier: dict[uuid.UUID, float] = field(default_factory=dict)
    over_lubrication_severity: dict[uuid.UUID, float] = field(default_factory=dict)
    bearing_wear_target_health: dict[uuid.UUID, float] = field(default_factory=dict)
    sensor_drift_bias: dict[uuid.UUID, float] = field(default_factory=dict)
    sensor_dropout: set[uuid.UUID] = field(default_factory=set)
    network_loss_machines: set[uuid.UUID] = field(default_factory=set)
    low_reservoir_targets: dict[uuid.UUID, float] = field(default_factory=dict)
    """reservoir_id -> target level_percent, applied ONCE at the instant an instance first
    becomes active (Phase 4 brief §10: a low reservoir is a starting condition that then
    plays out physically, not a continuous per-tick force)."""


def _restriction_offset(severity: float, params: dict[str, float]) -> float:
    return severity * params.get("max_restriction_factor", 0.8)


def _leakage_offset(severity: float, params: dict[str, float]) -> float:
    return severity * params.get("max_leakage_factor", 0.5)


def _pump_efficiency_offset(severity: float, params: dict[str, float]) -> float:
    return severity * params.get("max_efficiency_loss", 0.4)


def _volume_multiplier(severity: float, params: dict[str, float]) -> float:
    return 1.0 + severity * params.get("max_extra_volume_fraction", 1.0)


def _bearing_wear_target_health(severity: float, params: dict[str, float]) -> float:
    max_loss = params.get("max_health_loss", 0.6)
    return max(0.0, 1.0 - severity * max_loss)


def _sensor_drift_delta(severity: float, params: dict[str, float], range_span: float) -> float:
    """Sensor Drift is specified as a *fraction of the sensor's own configured valid
    range* (`max_bias_fraction_of_range`), not an absolute unit value — a magnitude that
    makes sense for a pressure sensor (bar) would be meaningless for an RPM sensor. `sign`
    (+1.0/-1.0) selects positive vs. negative drift (Phase 4 brief §12)."""
    fraction = params.get("max_bias_fraction_of_range", 0.1)
    sign = 1.0 if params.get("sign", 1.0) >= 0 else -1.0
    return sign * severity * fraction * range_span


def build_effects(
    instances: list[ScenarioInstance],
    topology: MachineTopology,
    config: EngineeringConfig,
    activation_edge: set[str],
) -> ScenarioEffects:
    """Build one tick's `ScenarioEffects` from every currently-active instance.

    `activation_edge` is the set of `instance_id`s that transitioned from inactive to
    active *this tick* (computed by the scheduler) — used only to fire the one-shot Low
    Reservoir initial-condition effect exactly once per instance.

    Multi-fault precedence (Phase 4 brief §16, docs/SCENARIO_ENGINE.md §6):
    - Numeric offsets on independent parameters of the same target (e.g. a circuit's
      restriction *and* leakage) always compose — they represent physically independent
      phenomena.
    - Multiple instances offsetting the *same* parameter of the same target (e.g. two
      restriction-type scenarios on one circuit) sum additively; the receiving physics
      function still clips to its valid physical range, so composition can saturate but
      never overflow.
    - For sensor observability this tick, `NETWORK_FAILURE` (whole-machine communication
      loss) outranks `SENSOR_DROPOUT` (single-sensor loss), which outranks `SENSOR_DRIFT`
      (the sensor is still reporting, just biased) — a sensor that isn't reporting at all
      has no drifted value to report, and a machine with no connectivity has no working
      sensors regardless of their individual state.
    """
    effects = ScenarioEffects()

    for instance in instances:
        if not instance.is_active:
            continue
        severity = instance.severity
        params = instance.definition.effect_params
        target_id = instance.target_id
        stype = instance.scenario_type

        if stype == ScenarioType.GRADUAL_RESTRICTION or stype == ScenarioType.SUDDEN_BLOCKAGE:
            effects.circuit_restriction_offset[target_id] = effects.circuit_restriction_offset.get(
                target_id, 0.0
            ) + _restriction_offset(severity, params)

        elif stype == ScenarioType.LEAKAGE:
            effects.circuit_leakage_offset[target_id] = effects.circuit_leakage_offset.get(
                target_id, 0.0
            ) + _leakage_offset(severity, params)

        elif stype == ScenarioType.PUMP_DEGRADATION:
            # target_id is a Pump id; the pump's efficiency lives on the owning
            # LubricationSystemState, so resolve pump -> lubrication_system here.
            ls_id = _lubrication_system_id_for_pump(topology, target_id)
            if ls_id is not None:
                effects.pump_efficiency_offset[ls_id] = effects.pump_efficiency_offset.get(
                    ls_id, 0.0
                ) + _pump_efficiency_offset(severity, params)

        elif stype == ScenarioType.OVER_LUBRICATION:
            effects.volume_multiplier[target_id] = max(
                effects.volume_multiplier.get(target_id, 1.0), _volume_multiplier(severity, params)
            )
            effects.over_lubrication_severity[target_id] = max(
                effects.over_lubrication_severity.get(target_id, 0.0), severity
            )

        elif stype == ScenarioType.INDEPENDENT_BEARING_FAULT:
            existing = effects.bearing_wear_target_health.get(target_id, 1.0)
            effects.bearing_wear_target_health[target_id] = min(
                existing, _bearing_wear_target_health(severity, params)
            )

        elif stype == ScenarioType.SENSOR_DRIFT:
            sensor_type = _sensor_type_by_id(topology).get(target_id)
            sensor_config = config.sensors.get(sensor_type) if sensor_type else None
            if sensor_config is not None:
                low, high = sensor_config.valid_range
                base = instance.drift_base_bias or 0.0
                effects.sensor_drift_bias[target_id] = base + _sensor_drift_delta(
                    severity, params, high - low
                )

        elif stype == ScenarioType.SENSOR_DROPOUT:
            if severity > 0.0:
                effects.sensor_dropout.add(target_id)

        elif stype == ScenarioType.NETWORK_FAILURE:
            if severity > 0.0:
                effects.network_loss_machines.add(target_id)

        elif stype == ScenarioType.LOW_RESERVOIR and instance.instance_id in activation_edge:
            # severity scales how low the one-shot initial level is set: severity 0 leaves
            # the reservoir at its normal starting level, severity 1.0 sets it all the way
            # down to `min_target_level_percent`.
            min_target = params.get("min_target_level_percent", 3.0)
            effects.low_reservoir_targets[target_id] = 100.0 - severity * (100.0 - min_target)

    return effects


def _lubrication_system_id_for_pump(
    topology: MachineTopology, pump_id: uuid.UUID
) -> uuid.UUID | None:
    ls = topology.lubrication_system
    if ls is not None and ls.pump.id == pump_id:
        return ls.id
    return None


def _sensor_type_by_id(topology: MachineTopology) -> dict[uuid.UUID, str]:
    return {s.id: s.sensor_type for s in topology.sensors}
