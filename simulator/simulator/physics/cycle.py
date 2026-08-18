"""Lubrication cycle state machine (Phase 3 brief §6).

A cycle progresses IDLE -> PUMP_START -> PRESSURE_BUILD -> FLOW_DELIVERY -> COMPLETING ->
IDLE. Pressure rises during PRESSURE_BUILD, lubricant is delivered (and the reservoir
consumed) during FLOW_DELIVERY, and pressure decays back down during COMPLETING — the
pressure/flow *shape* over time is represented explicitly, not collapsed into one constant
reading per cycle. A cycle only starts while the machine is actually running, and only one
lubrication system's controller instance drives it — the cycle interval is measured in
wall/simulation time, not machine runtime, matching a timer-based controller
(`docs/ASSET_HIERARCHY.md` §10 seed data: half of demo controllers are timer-based).
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass

from simulator.config.loader import CircuitConfig, CycleConfig, PumpConfig
from simulator.domain.enums import CyclePhase, CycleResult, OperatingState
from simulator.domain.state import LubricationSystemState
from simulator.domain.topology import CircuitTopology
from simulator.physics import circuit as circuit_physics
from simulator.physics import pump as pump_physics


@dataclass(frozen=True, slots=True)
class CycleEvent:
    event_type: str  # "cycle_started" | "cycle_completed"
    cycle_id: str
    result: CycleResult | None = None


_PUMP_START_DELAY_S = 1.0
_COMPLETING_SETTLE_S = 2.0


class LubricationCycleController:
    """One instance per `LubricationSystem`. Owns cycle timing/phase progression and drives
    the pump + circuit physics for that system every tick."""

    def __init__(
        self,
        lubrication_system_id: str,
        circuits: tuple[CircuitTopology, ...],
        cycle_config: CycleConfig,
        pump_config: PumpConfig,
        circuit_config: CircuitConfig,
    ) -> None:
        self._lubrication_system_id = lubrication_system_id
        self._circuits = circuits
        self._cycle_config = cycle_config
        self._pump_config = pump_config
        self._circuit_config = circuit_config
        self._cycle_counter = 0

    def step(
        self,
        state: LubricationSystemState,
        operating_state: OperatingState,
        dt_s: float,
        rng: random.Random,
        *,
        restriction_offsets: dict[uuid.UUID, float] | None = None,
        leakage_offsets: dict[uuid.UUID, float] | None = None,
        reservoir_availability: float = 1.0,
        volume_multiplier: float = 1.0,
    ) -> CycleEvent | None:
        """`restriction_offsets`/`leakage_offsets` (per-circuit-id) and
        `reservoir_availability`/`volume_multiplier` are the Phase 4 scenario integration
        points (docs/SCENARIO_ENGINE.md §5) — all default to "no effect," reproducing exact
        Phase 3 behavior when no scenario is active."""
        for circuit_topology in self._circuits:
            circuit_state = state.circuits[circuit_topology.id]
            circuit_physics.step_natural_variation(
                circuit_state,
                self._circuit_config,
                dt_s,
                rng,
                restriction_offset=(restriction_offsets or {}).get(circuit_topology.id, 0.0),
                leakage_offset=(leakage_offsets or {}).get(circuit_topology.id, 0.0),
            )

        cycle = state.cycle
        pump = state.pump

        if cycle.phase == CyclePhase.IDLE:
            cycle.since_last_cycle_s += dt_s
            interval_s = self._cycle_config.interval_minutes * 60.0
            if operating_state.is_running and cycle.since_last_cycle_s >= interval_s:
                self._cycle_counter += 1
                cycle.cycle_id = f"{self._lubrication_system_id}:{self._cycle_counter}"
                cycle.phase = CyclePhase.PUMP_START
                cycle.phase_elapsed_s = 0.0
                cycle.cycle_elapsed_s = 0.0
                cycle.since_last_cycle_s = 0.0
                cycle.result = None
                cycle.delivered_volume_cm3 = 0.0
                for circuit_topology in self._circuits:
                    cs = state.circuits[circuit_topology.id]
                    cs.last_delivery_confirmed = False
                    cs.delivered_volume_cm3 = 0.0
                pump.is_on = True
                pump_physics.step_pressure(pump, 0.0, self._pump_config, dt_s)
                pump_physics.step_current(pump, self._pump_config)
                pump_physics.step_runtime(pump, dt_s)
                return CycleEvent(event_type="cycle_started", cycle_id=cycle.cycle_id)

            pump.is_on = False
            pump_physics.step_pressure(pump, 0.0, self._pump_config, dt_s)
            pump_physics.step_current(pump, self._pump_config)
            return None

        cycle.phase_elapsed_s += dt_s
        cycle.cycle_elapsed_s += dt_s
        timed_out = cycle.cycle_elapsed_s >= self._cycle_config.max_duration_s

        # The distributor splits metered lubricant across circuits (docs/DOMAIN_MODEL.md
        # §2.1) — approximated here as an equal share of the pump's nominal flow capacity
        # per circuit, a reduced-order simplification documented in docs/SIMULATOR.md §9.
        per_circuit_flow_capacity = self._pump_config.nominal_flow_capacity_cm3_min / max(
            1, len(self._circuits)
        )
        operating_points = {
            ct.id: circuit_physics.solve_operating_point(
                state.circuits[ct.id],
                self._circuit_config,
                self._pump_config.base_operating_pressure_bar,
                per_circuit_flow_capacity,
                pump.efficiency,
            )
            for ct in self._circuits
        }
        required_pressure = max(op.required_pressure_bar for op in operating_points.values())

        if cycle.phase == CyclePhase.PUMP_START:
            pump.is_on = True
            if cycle.phase_elapsed_s >= _PUMP_START_DELAY_S:
                cycle.phase = CyclePhase.PRESSURE_BUILD
                cycle.phase_elapsed_s = 0.0

        elif cycle.phase == CyclePhase.PRESSURE_BUILD:
            pump.is_on = True
            reached = (
                pump.pressure_bar
                >= self._cycle_config.pressure_build_target_ratio * required_pressure
            )
            if reached:
                cycle.phase = CyclePhase.FLOW_DELIVERY
                cycle.phase_elapsed_s = 0.0
            elif timed_out:
                cycle.result = CycleResult.FAILED
                cycle.phase = CyclePhase.COMPLETING
                cycle.phase_elapsed_s = 0.0
                pump.is_on = False

        elif cycle.phase == CyclePhase.FLOW_DELIVERY:
            pump.is_on = True
            total_raw_flow_cm3_min = 0.0
            for ct in self._circuits:
                cs = state.circuits[ct.id]
                op = operating_points[ct.id]
                # reservoir_availability (Low Reservoir) and volume_multiplier
                # (Over-Lubrication) both act on the pump's output side, so they scale raw
                # and delivered flow proportionally; leakage's raw-vs-delivered split
                # (module docstring) is already baked into `op` itself.
                effective_raw = op.raw_flow_cm3_min * reservoir_availability * volume_multiplier
                effective_delivered = (
                    op.delivered_flow_cm3_min * reservoir_availability * volume_multiplier
                )
                cs.flow_cm3_min = effective_delivered
                total_raw_flow_cm3_min += effective_raw
                cs.delivered_volume_cm3 += effective_delivered * (dt_s / 60.0)
            cycle.delivered_volume_cm3 += total_raw_flow_cm3_min * (dt_s / 60.0)

            stroke_period = self._cycle_config.piston_stroke_period_s
            if (
                stroke_period > 0
                and int(cycle.phase_elapsed_s / stroke_period) > cycle.piston_position
            ):
                cycle.piston_position += 1

            target_volume = self._cycle_config.base_volume_per_cycle_cm3
            delivered_enough = cycle.delivered_volume_cm3 >= target_volume
            if delivered_enough or timed_out:
                ratio = cycle.delivered_volume_cm3 / target_volume if target_volume > 0 else 0.0
                if ratio >= self._cycle_config.success_delivery_ratio:
                    cycle.result = CycleResult.SUCCESS
                elif ratio >= self._cycle_config.partial_delivery_ratio:
                    cycle.result = CycleResult.PARTIAL
                else:
                    cycle.result = CycleResult.FAILED
                cycle.phase = CyclePhase.COMPLETING
                cycle.phase_elapsed_s = 0.0
                pump.is_on = False
                # Per-circuit delivery confirmation (drives that circuit's bearing(s)'
                # lubrication_effectiveness via on_cycle_result) is judged against this
                # circuit's own fair share of the target volume — not merely "any nonzero
                # flow at all" — so Leakage, which reduces delivered volume without
                # reducing it to zero, actually shows up here (docs/SCENARIO_ENGINE.md §5).
                per_circuit_target = target_volume / max(1, len(self._circuits))
                for ct in self._circuits:
                    cs = state.circuits[ct.id]
                    circuit_ratio = (
                        cs.delivered_volume_cm3 / per_circuit_target
                        if per_circuit_target > 0
                        else 0.0
                    )
                    cs.last_delivery_confirmed = (
                        circuit_ratio >= self._cycle_config.success_delivery_ratio
                    )
                    cs.flow_cm3_min = 0.0

        elif cycle.phase == CyclePhase.COMPLETING:
            pump.is_on = False
            if cycle.phase_elapsed_s >= _COMPLETING_SETTLE_S:
                completed_id = cycle.cycle_id
                result = cycle.result
                cycle.phase = CyclePhase.IDLE
                cycle.phase_elapsed_s = 0.0
                cycle.piston_position = 0
                pump_physics.step_pressure(pump, 0.0, self._pump_config, dt_s)
                pump_physics.step_current(pump, self._pump_config)
                pump_physics.step_runtime(pump, dt_s)
                assert completed_id is not None
                return CycleEvent(
                    event_type="cycle_completed", cycle_id=completed_id, result=result
                )

        target_pressure = required_pressure if pump.is_on else 0.0
        pump_physics.step_pressure(pump, target_pressure, self._pump_config, dt_s)
        pump_physics.step_current(pump, self._pump_config)
        pump_physics.step_runtime(pump, dt_s)
        return None
