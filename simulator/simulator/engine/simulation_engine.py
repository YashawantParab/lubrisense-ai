"""`SimulationEngine` — ties domain state, physics, sensor models, and the Phase 4 scenario
engine together into a deterministic, steppable simulation for one machine (Phase 3 brief
§1, §16; Phase 4 brief §1-§2).

One `step()` call advances hidden physical state by `step_seconds` of simulated time and
returns the observable `SimulationReading`s derived from that state plus one
`GroundTruthRecord` (kept separate — §18). All randomness flows through a single
`random.Random(seed)` instance created here and threaded through every physics/sensor/
scenario call, which is the entire determinism mechanism: same seed + same config + same
topology + same scenario plan + same start state => byte-identical output.

Scenario integration (docs/SCENARIO_ENGINE.md §3): each tick, the `ScenarioScheduler` is
advanced and produces a `ScenarioEffects` snapshot; this engine applies that snapshot by
passing its values into the *existing* Phase 3 physics functions as additional
offset/target inputs (`step_natural_variation(restriction_offset=...)`,
`step_efficiency(efficiency_offset=...)`, `apply_independent_wear(target_health=...)`, the
cycle controller's `restriction_offsets`/`reservoir_availability`/`volume_multiplier`, and
Sensor Drift/Dropout/Network Failure's effect on reading collection). No physics function
branches on "is a scenario active" — they only ever see a number that happens to be
different from its healthy default.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from logging import Logger

from simulator.config.loader import EngineeringConfig
from simulator.domain.enums import (
    CyclePhase,
    CycleResult,
    NetworkState,
    OperatingState,
    SensorQuality,
)
from simulator.domain.state import (
    BearingState,
    CircuitState,
    LubricationSystemState,
    MachineSimulationState,
    MachineState,
    PumpState,
    ReservoirState,
    SensorState,
)
from simulator.domain.topology import MachineTopology, SensorTopology
from simulator.engine.logging_utils import get_simulator_logger, log_event
from simulator.engine.output import (
    BearingGroundTruth,
    CircuitGroundTruth,
    GroundTruthRecord,
    ScenarioGroundTruth,
    SimulationReading,
)
from simulator.physics import bearing as bearing_physics
from simulator.physics import circuit as circuit_physics
from simulator.physics import pump as pump_physics
from simulator.physics import reservoir as reservoir_physics
from simulator.physics.cycle import LubricationCycleController
from simulator.physics.machine import OperatingProfile, step_ambient_temperature
from simulator.scenarios import HEALTHY
from simulator.scenarios.effects import ScenarioEffects
from simulator.scenarios.instance import ScenarioInstance
from simulator.scenarios.scheduler import AutoRefillPolicy, ScenarioScheduler
from simulator.scenarios.types import ScenarioType
from simulator.sensors import models as sensor_models


class SimulationInvariantError(RuntimeError):
    """Raised when hidden state leaves its physically-valid domain (NaN/inf/negative
    impossible quantity) — see Phase 3 brief §24. This should never happen for the healthy
    scenario; if it does, it indicates a modeling bug, not something to silently clamp."""


@dataclass(frozen=True, slots=True)
class SimulationTick:
    readings: list[SimulationReading]
    ground_truth: GroundTruthRecord


class SimulationEngine:
    def __init__(
        self,
        topology: MachineTopology,
        config: EngineeringConfig,
        seed: int,
        start_time: datetime,
        step_seconds: float | None = None,
        logger: Logger | None = None,
        scenario_instances: list[ScenarioInstance] | None = None,
        refill_policy: AutoRefillPolicy | None = None,
    ) -> None:
        self._topology = topology
        self._config = config
        self.seed = seed
        self._rng = random.Random(seed)
        self.step_seconds = step_seconds or config.simulation.default_step_seconds
        self._start_time = start_time
        self._sim_seconds = 0.0
        self._logger = logger or get_simulator_logger()

        self._state = self._build_initial_state()
        self._operating_profile = OperatingProfile(
            config.operating_profile, config.machine, topology.machine_type, self._rng
        )
        self._cycle_controller: LubricationCycleController | None = None
        if topology.lubrication_system is not None:
            self._cycle_controller = LubricationCycleController(
                lubrication_system_id=str(topology.lubrication_system.id),
                circuits=topology.lubrication_system.circuits,
                cycle_config=config.cycle,
                pump_config=config.pump,
                circuit_config=config.circuit,
            )

        self._scheduler = ScenarioScheduler(
            scenario_instances or [], topology, config, refill_policy
        )

    @property
    def sim_seconds(self) -> float:
        return self._sim_seconds

    @property
    def state(self) -> MachineSimulationState:
        return self._state

    @property
    def scheduler(self) -> ScenarioScheduler:
        return self._scheduler

    # -- setup ---------------------------------------------------------------

    def _build_initial_state(self) -> MachineSimulationState:
        cfg = self._config
        machine_state = MachineState(
            operating_state=OperatingState.STOPPED,
            ambient_temperature_c=cfg.machine.ambient_temperature_c.mean,
        )

        bearing_states = {
            b.id: BearingState(
                bearing_id=b.id,
                temperature_c=cfg.bearing.temperature_baseline_c,
                vibration_rms_mm_s=cfg.bearing.vibration_baseline_mm_s,
                vibration_peak_mm_s=cfg.bearing.vibration_baseline_mm_s
                * cfg.bearing.vibration_peak_to_rms_ratio,
            )
            for b in self._topology.bearings
        }

        lubrication_system_state: LubricationSystemState | None = None
        if self._topology.lubrication_system is not None:
            ls = self._topology.lubrication_system
            capacity = ls.reservoir.capacity_demo or cfg.reservoir.default_capacity_l
            reservoir_state = ReservoirState(
                capacity_l=capacity,
                quantity_l=capacity,
                lubricant_temperature_c=cfg.machine.ambient_temperature_c.mean,
            )
            circuit_states = {
                c.id: CircuitState(
                    restriction_factor=cfg.circuit.default_restriction_factor,
                    leakage_factor=cfg.circuit.default_leakage_factor,
                )
                for c in ls.circuits
            }
            lubrication_system_state = LubricationSystemState(
                reservoir=reservoir_state,
                pump=PumpState(efficiency=cfg.pump.efficiency_default),
                circuits=circuit_states,
            )

        sensor_states = {
            s.id: SensorState(
                sensor_id=s.id,
                bias=sensor_models.draw_initial_bias(cfg.sensors[s.sensor_type], self._rng),
            )
            for s in self._topology.sensors
            if s.sensor_type in cfg.sensors
        }

        return MachineSimulationState(
            machine=machine_state,
            bearings=bearing_states,
            lubrication_system=lubrication_system_state,
            sensors=sensor_states,
        )

    # -- stepping --------------------------------------------------------------

    def step(self) -> SimulationTick:
        dt = self.step_seconds
        state = self._state

        prev_operating_state = state.machine.operating_state
        self._operating_profile.step(state.machine, self._sim_seconds, dt)
        if state.machine.operating_state != prev_operating_state:
            log_event(
                self._logger,
                "state_transition",
                f"{self._topology.asset_code} operating state {prev_operating_state} -> "
                f"{state.machine.operating_state}",
                asset_code=self._topology.asset_code,
                from_state=str(prev_operating_state),
                to_state=str(state.machine.operating_state),
                sim_seconds=self._sim_seconds,
            )
        step_ambient_temperature(state.machine, self._config.machine, self._sim_seconds, self._rng)

        self._scheduler.advance(self._sim_seconds, dt)
        self._capture_new_drift_bases()
        effects = self._scheduler.build_effects()

        cycle_completed_result: CycleResult | None = None
        refill_event = False
        if self._cycle_controller is not None and state.lubrication_system is not None:
            ls_state = state.lubrication_system
            ls_topology = self._topology.lubrication_system
            assert ls_topology is not None

            if ls_topology.reservoir.id in effects.low_reservoir_targets:
                target_percent = effects.low_reservoir_targets[ls_topology.reservoir.id]
                reservoir_physics.refill(ls_state.reservoir, to_percent=target_percent)
                log_event(
                    self._logger,
                    "low_reservoir_initialized",
                    f"{self._topology.asset_code} reservoir set to {target_percent:.1f}% "
                    "(Low Reservoir scenario activation)",
                    asset_code=self._topology.asset_code,
                    target_percent=target_percent,
                    sim_seconds=self._sim_seconds,
                )

            reservoir_availability = reservoir_physics.availability_factor(
                ls_state.reservoir, self._config.reservoir
            )
            volume_multiplier = effects.volume_multiplier.get(ls_topology.id, 1.0)

            prev_delivered = ls_state.cycle.delivered_volume_cm3
            event = self._cycle_controller.step(
                ls_state,
                state.machine.operating_state,
                dt,
                self._rng,
                restriction_offsets=effects.circuit_restriction_offset,
                leakage_offsets=effects.circuit_leakage_offset,
                reservoir_availability=reservoir_availability,
                volume_multiplier=volume_multiplier,
            )
            delivered_delta = ls_state.cycle.delivered_volume_cm3 - prev_delivered
            if delivered_delta > 0:
                reservoir_physics.consume(ls_state.reservoir, delivered_delta)

            pump_physics.step_efficiency(
                ls_state.pump,
                self._config.pump,
                dt,
                self._rng,
                efficiency_offset=effects.pump_efficiency_offset.get(ls_topology.id, 0.0),
            )
            reservoir_physics.step_lubricant_temperature(
                ls_state.reservoir, state.machine.ambient_temperature_c, ls_state.pump.is_on, dt
            )

            level_percent = reservoir_physics.level_percent(ls_state.reservoir)
            if self._scheduler.check_refill(level_percent, self._sim_seconds):
                reservoir_physics.refill(
                    ls_state.reservoir, to_percent=self._scheduler.refill_to_percent
                )
                refill_event = True
                log_event(
                    self._logger,
                    "refill_event",
                    f"{self._topology.asset_code} reservoir refilled to "
                    f"{self._scheduler.refill_to_percent:.1f}%",
                    asset_code=self._topology.asset_code,
                    sim_seconds=self._sim_seconds,
                )

            if event is not None:
                log_event(
                    self._logger,
                    event.event_type,
                    f"{self._topology.asset_code} {event.event_type} {event.cycle_id}",
                    asset_code=self._topology.asset_code,
                    cycle_id=event.cycle_id,
                    result=str(event.result) if event.result else None,
                    sim_seconds=self._sim_seconds,
                )
                if event.event_type == "cycle_completed":
                    cycle_completed_result = event.result
                    self._apply_cycle_result_to_bearings(ls_state)

        over_lubrication_severity = 0.0
        if self._topology.lubrication_system is not None:
            over_lubrication_severity = effects.over_lubrication_severity.get(
                self._topology.lubrication_system.id, 0.0
            )

        for bearing_state in state.bearings.values():
            bearing_physics.step_temperature(
                bearing_state,
                self._config.bearing,
                state.machine.load_percent,
                state.machine.ambient_temperature_c,
                dt,
                over_lubrication_severity=over_lubrication_severity,
            )
            bearing_physics.step_vibration(
                bearing_state, self._config.bearing, state.machine.load_percent, dt
            )
            bearing_physics.step_health(bearing_state, self._config.bearing, dt)
            wear_target = effects.bearing_wear_target_health.get(bearing_state.bearing_id)
            if wear_target is not None:
                bearing_physics.apply_independent_wear(
                    bearing_state, self._config.bearing, wear_target, dt
                )

        self._validate_state()

        readings = self._collect_readings(cycle_completed_result, effects)
        ground_truth = self._collect_ground_truth(effects, refill_event)

        self._sim_seconds += dt
        return SimulationTick(readings=readings, ground_truth=ground_truth)

    def run(self, duration_seconds: float) -> Iterator[SimulationTick]:
        log_event(
            self._logger,
            "simulation_started",
            f"simulation started for {self._topology.asset_code}",
            asset_code=self._topology.asset_code,
            seed=self.seed,
            duration_seconds=duration_seconds,
            step_seconds=self.step_seconds,
            scenarios=[i.definition.name for i in self._scheduler.instances],
        )
        total_ticks = int(round(duration_seconds / self.step_seconds))
        for _ in range(total_ticks):
            yield self.step()
        log_event(
            self._logger,
            "simulation_stopped",
            f"simulation stopped for {self._topology.asset_code}",
            asset_code=self._topology.asset_code,
            sim_seconds=self._sim_seconds,
        )

    # -- internals ---------------------------------------------------------------

    def _capture_new_drift_bases(self) -> None:
        """Sensor Drift (Phase 4 brief §12) must offset the sensor's *existing* fixed
        calibration bias, not replace it — capture that starting point exactly once, the
        instant the instance activates, from the live `SensorState` (not from the
        scenario/topology layer, which has no visibility into simulation state)."""
        for instance in self._scheduler.instances:
            if (
                instance.instance_id in self._scheduler.last_activation_edge
                and instance.scenario_type == ScenarioType.SENSOR_DRIFT
                and instance.drift_base_bias is None
            ):
                sensor_state = self._state.sensors.get(instance.target_id)
                if sensor_state is not None:
                    instance.drift_base_bias = sensor_state.bias

    def _apply_cycle_result_to_bearings(self, ls_state: LubricationSystemState) -> None:
        assert self._topology.lubrication_system is not None
        for circuit_topology in self._topology.lubrication_system.circuits:
            circuit_state = ls_state.circuits[circuit_topology.id]
            delivered = circuit_state.last_delivery_confirmed
            for lp in circuit_topology.lubrication_points:
                if lp.bearing_id is not None and lp.bearing_id in self._state.bearings:
                    bearing_physics.on_cycle_result(
                        self._state.bearings[lp.bearing_id], self._config.bearing, delivered
                    )

    def _resolve_true_value(
        self, sensor: SensorTopology, cycle_completed_result: CycleResult | None
    ) -> float | None:
        state = self._state
        mt = sensor.sensor_type

        if mt == "RPM":
            return state.machine.rpm
        if mt == "LOAD":
            return state.machine.load_percent
        if mt == "BEARING_TEMPERATURE":
            b = state.bearings.get(sensor.attached_entity_id)
            return b.temperature_c if b else None
        if mt == "VIBRATION_RMS":
            b = state.bearings.get(sensor.attached_entity_id)
            return b.vibration_rms_mm_s if b else None
        if mt == "VIBRATION_PEAK":
            b = state.bearings.get(sensor.attached_entity_id)
            return b.vibration_peak_mm_s if b else None

        ls_state = state.lubrication_system
        if ls_state is None:
            return None
        if mt == "RESERVOIR_LEVEL":
            return reservoir_physics.level_percent(ls_state.reservoir)
        if mt == "LUBRICANT_TEMPERATURE":
            return ls_state.reservoir.lubricant_temperature_c
        if mt == "PUMP_CURRENT":
            return ls_state.pump.motor_current_a
        if mt == "PUMP_RUNTIME":
            return ls_state.pump.runtime_s
        if mt == "PRESSURE":
            circuit_state = ls_state.circuits.get(sensor.attached_entity_id)
            if circuit_state is None:
                return None
            return circuit_physics.circuit_backpressure_bar(
                ls_state.pump.pressure_bar, circuit_state, self._config.circuit
            )
        if mt == "FLOW":
            circuit_state = ls_state.circuits.get(sensor.attached_entity_id)
            return circuit_state.flow_cm3_min if circuit_state else None
        if mt == "CYCLE_COMPLETION":
            return 1.0 if cycle_completed_result == CycleResult.SUCCESS else 0.0
        if mt == "PISTON_MOVEMENT":
            return float(ls_state.cycle.piston_position)
        return None

    def _collect_readings(
        self, cycle_completed_result: CycleResult | None, effects: ScenarioEffects
    ) -> list[SimulationReading]:
        state = self._state
        timestamp = self._start_time + timedelta(seconds=self._sim_seconds)
        cycle_id = state.lubrication_system.cycle.cycle_id if state.lubrication_system else None
        cycle_phase = (
            state.lubrication_system.cycle.phase.value
            if state.lubrication_system
            else CyclePhase.IDLE.value
        )
        network_loss_active = self._topology.id in effects.network_loss_machines

        def make_reading(
            sensor: SensorTopology,
            true_value: float,
            observed_value: float | None,
            unit: str,
            quality: str,
        ) -> SimulationReading:
            return SimulationReading(
                simulation_timestamp=timestamp,
                tenant_id=self._topology.tenant_id,
                asset_id=self._topology.id,
                component_id=sensor.attached_entity_id,
                sensor_id=sensor.id,
                measurement_type=sensor.sensor_type,
                true_value=true_value,
                observed_value=observed_value,
                unit=unit,
                quality=quality,
                operating_state=state.machine.operating_state.value,
                cycle_id=cycle_id,
                simulation_state=cycle_phase,
            )

        readings: list[SimulationReading] = []
        for sensor in self._topology.sensors:
            sensor_config = self._config.sensors.get(sensor.sensor_type)
            if sensor_config is None:
                continue
            true_value = self._resolve_true_value(sensor, cycle_completed_result)
            if true_value is None:
                continue

            # Network Failure and Sensor Dropout preserve the physical `true_value` (the
            # simulator keeps computing it) while making the *observation* unavailable —
            # never a fabricated numeric value (Phase 4 brief §13-§14; precedence per
            # docs/SCENARIO_ENGINE.md §6: whole-machine Network Failure outranks a single
            # Sensor Dropout).
            if network_loss_active:
                readings.append(
                    make_reading(
                        sensor,
                        true_value,
                        None,
                        sensor_config.unit,
                        SensorQuality.COMMUNICATION_LOSS.value,
                    )
                )
                continue
            if sensor.id in effects.sensor_dropout:
                readings.append(
                    make_reading(
                        sensor, true_value, None, sensor_config.unit, SensorQuality.MISSING.value
                    )
                )
                continue

            sensor_state = state.sensors[sensor.id]
            effective_bias = effects.sensor_drift_bias.get(sensor.id, sensor_state.bias)
            observation = sensor_models.observe(
                true_value, effective_bias, sensor_config, self._rng
            )
            readings.append(
                make_reading(
                    sensor,
                    observation.true_value,
                    observation.observed_value,
                    observation.unit,
                    observation.quality.value,
                )
            )
        return readings

    def _collect_ground_truth(
        self, effects: ScenarioEffects, refill_event: bool
    ) -> GroundTruthRecord:
        state = self._state
        timestamp = self._start_time + timedelta(seconds=self._sim_seconds)
        ls_state = state.lubrication_system

        scenario_records = tuple(
            ScenarioGroundTruth(
                instance_id=instance.instance_id,
                scenario_type=instance.scenario_type.value,
                lifecycle_state=instance.lifecycle_state.value,
                severity=instance.severity,
                target_type=instance.definition.target_type.value,
                target_id=instance.target_id,
                started_at_sim_seconds=instance.active_since_seconds,
                elapsed_seconds=(
                    self._sim_seconds - instance.active_since_seconds
                    if instance.active_since_seconds is not None
                    else 0.0
                ),
            )
            for instance in self._scheduler.instances
            if instance.is_active
        )

        if scenario_records:
            primary = max(scenario_records, key=lambda s: s.severity)
            scenario_label = primary.scenario_type
            severity_label = primary.lifecycle_state
            affected_component = str(primary.target_id)
        else:
            scenario_label = HEALTHY.name
            severity_label = "NONE"
            affected_component = None

        network_state = (
            NetworkState.DISCONNECTED.value
            if self._topology.id in effects.network_loss_machines
            else NetworkState.CONNECTED.value
        )
        reservoir_level_state = (
            reservoir_physics.level_state(ls_state.reservoir, self._config.reservoir).value
            if ls_state
            else None
        )

        return GroundTruthRecord(
            simulation_timestamp=timestamp,
            tenant_id=self._topology.tenant_id,
            asset_id=self._topology.id,
            scenario=scenario_label,
            severity=severity_label,
            affected_component=affected_component,
            operating_state=state.machine.operating_state.value,
            load_percent=state.machine.load_percent,
            ambient_temperature_c=state.machine.ambient_temperature_c,
            pump_efficiency=ls_state.pump.efficiency if ls_state else None,
            reservoir_quantity_l=ls_state.reservoir.quantity_l if ls_state else None,
            reservoir_capacity_l=ls_state.reservoir.capacity_l if ls_state else None,
            reservoir_level_state=reservoir_level_state,
            network_state=network_state,
            refill_event=refill_event,
            bearings=tuple(
                BearingGroundTruth(
                    bearing_id=b.bearing_id,
                    lubrication_effectiveness=b.lubrication_effectiveness,
                    health=b.health,
                )
                for b in state.bearings.values()
            ),
            circuits=tuple(
                CircuitGroundTruth(
                    circuit_id=cid,
                    restriction_factor=cs.restriction_factor,
                    leakage_factor=cs.leakage_factor,
                )
                for cid, cs in (ls_state.circuits.items() if ls_state else {})
            ),
            scenarios=scenario_records,
        )

    def _validate_state(self) -> None:
        """Numerical-stability guard (Phase 3 brief §24): fail loudly on NaN/inf/impossible
        negative quantities rather than silently emitting bad data."""
        state = self._state
        checks: list[tuple[str, float]] = [
            ("machine.load_percent", state.machine.load_percent),
            ("machine.rpm", state.machine.rpm),
            ("machine.ambient_temperature_c", state.machine.ambient_temperature_c),
        ]
        for b in state.bearings.values():
            checks.append((f"bearing[{b.bearing_id}].temperature_c", b.temperature_c))
            checks.append((f"bearing[{b.bearing_id}].vibration_rms_mm_s", b.vibration_rms_mm_s))
            checks.append((f"bearing[{b.bearing_id}].health", b.health))
        if state.lubrication_system is not None:
            ls = state.lubrication_system
            checks.append(("reservoir.quantity_l", ls.reservoir.quantity_l))
            checks.append(("pump.pressure_bar", ls.pump.pressure_bar))
            checks.append(("pump.motor_current_a", ls.pump.motor_current_a))
            for cid, cs in ls.circuits.items():
                checks.append((f"circuit[{cid}].flow_cm3_min", cs.flow_cm3_min))

        for name, value in checks:
            if not math.isfinite(value):
                log_event(
                    self._logger,
                    "invalid_state",
                    f"non-finite value in {name}: {value}",
                    field=name,
                    value=str(value),
                    sim_seconds=self._sim_seconds,
                )
                raise SimulationInvariantError(
                    f"{name} became non-finite ({value}) at t={self._sim_seconds}s"
                )
            if (
                value < 0
                and name not in ("machine.ambient_temperature_c",)
                and "temperature" not in name
            ):
                log_event(
                    self._logger,
                    "invalid_state",
                    f"impossible negative value in {name}: {value}",
                    field=name,
                    value=value,
                    sim_seconds=self._sim_seconds,
                )
                raise SimulationInvariantError(
                    f"{name} went negative ({value}) at t={self._sim_seconds}s"
                )
