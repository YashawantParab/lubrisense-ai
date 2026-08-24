"""Hidden physical state — GROUND TRUTH, never exposed directly as observable telemetry.

Phase 3 brief §4 and §18: the simulator maintains these as its internal source of truth;
`simulator.sensors.models.SensorModel` derives observable readings from them, and
`simulator.engine.output.GroundTruthRecord` is the only channel these values are exported
through (see docs/SYNTHETIC_DATA_MODEL.md). Future ML phases must not receive these fields
as features — only the observed sensor readings.

All state is mutated in place by `simulator.physics.*` step functions once per simulation
tick; nothing here computes anything itself (state is data, physics is behavior).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from simulator.domain.enums import CyclePhase, CycleResult, OperatingState


@dataclass(slots=True)
class MachineState:
    """Whole-machine hidden state. `load` and `rpm` are percent-of-nominal / rpm; both are
    physical ground truth, not sensor readings (docs/SYNTHETIC_DATA_MODEL.md §2)."""

    operating_state: OperatingState = OperatingState.STOPPED
    load_percent: float = 0.0
    load_target_percent: float = 0.0
    rpm: float = 0.0
    ambient_temperature_c: float = 22.0
    state_seconds: float = 0.0  # time spent in current operating_state, seconds
    #: Driveline electrical power, kW — Lubrication Efficiency Intelligence
    #: (docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md, ADR-176). Lagged like
    #: temperature/vibration (`simulator.physics.power.step_power`), not an instantaneous
    #: function of load — real driveline power doesn't jump discontinuously either.
    power_kw: float = 0.0


@dataclass(slots=True)
class ReservoirState:
    capacity_l: float
    quantity_l: float
    lubricant_temperature_c: float = 22.0


@dataclass(slots=True)
class PumpState:
    efficiency: float = 0.97  # 1.0 = design nominal, demo synthetic assumption
    pressure_bar: float = 0.0
    motor_current_a: float = 0.0
    runtime_s: float = 0.0
    is_on: bool = False


@dataclass(slots=True)
class CircuitState:
    restriction_factor: float = 0.0  # 0 = clear, 1 = fully blocked
    leakage_factor: float = 0.0  # 0 = no leakage, 1 = total loss
    flow_cm3_min: float = 0.0
    last_delivery_confirmed: bool = False
    #: Running total of *delivered* (post-leak) volume for the in-progress cycle — reset at
    #: cycle start, compared against this circuit's target share at cycle completion to
    #: decide `last_delivery_confirmed`. Distinct from the aggregate, raw-flow-based
    #: `CycleState.delivered_volume_cm3` — see simulator.physics.circuit module docstring
    #: and docs/SCENARIO_ENGINE.md §5.
    delivered_volume_cm3: float = 0.0


@dataclass(slots=True)
class BearingState:
    bearing_id: uuid.UUID
    lubrication_effectiveness: float = 1.0  # 0..1, 1 = fully lubricated
    health: float = 1.0  # 0..1, 1 = perfect condition
    temperature_c: float = 38.0  # lagged, see physics.bearing
    vibration_rms_mm_s: float = 1.2  # lagged
    vibration_peak_mm_s: float = 1.8


@dataclass(slots=True)
class CycleState:
    """Current/most-recent lubrication cycle — see docs/SIMULATOR.md §6."""

    cycle_id: str | None = None
    phase: CyclePhase = CyclePhase.IDLE
    phase_elapsed_s: float = 0.0
    cycle_elapsed_s: float = 0.0
    since_last_cycle_s: float = 0.0
    result: CycleResult | None = None
    piston_position: int = 0  # increments per metering stroke during FLOW_DELIVERY
    delivered_volume_cm3: float = 0.0  # running total for the in-progress cycle


@dataclass(slots=True)
class SensorState:
    """Per-sensor measurement-effect state (bias is fixed for the run's seed, drawn once
    at initialization — see docs/SIMULATOR.md §11)."""

    sensor_id: uuid.UUID
    bias: float = 0.0


@dataclass(slots=True)
class LubricationSystemState:
    reservoir: ReservoirState
    pump: PumpState = field(default_factory=PumpState)
    circuits: dict[uuid.UUID, CircuitState] = field(default_factory=dict)
    cycle: CycleState = field(default_factory=CycleState)


@dataclass(slots=True)
class MachineSimulationState:
    """The full hidden state for one simulated machine — the ground-truth object the
    engine mutates every tick."""

    machine: MachineState
    bearings: dict[uuid.UUID, BearingState]
    lubrication_system: LubricationSystemState | None
    sensors: dict[uuid.UUID, SensorState]
