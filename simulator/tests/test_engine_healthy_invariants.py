from __future__ import annotations

import math

from simulator.domain.enums import CyclePhase, OperatingState
from simulator.engine.simulation_engine import SimulationEngine


def test_healthy_two_hour_run_satisfies_all_invariants(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    engine = SimulationEngine(
        topology=flagship_topology,
        config=engineering_config,
        seed=7,
        start_time=fixed_start_time,
        step_seconds=5.0,
    )

    prev_reservoir_l = engine.state.lubrication_system.reservoir.quantity_l
    saw_running = False
    saw_stopped = False
    saw_flow_delivery = False
    all_readings = []

    # 10 simulated hours at a 5s step: the configured demo shift starts at simulated hour 6
    # (docs/SIMULATOR.md §4), so this window is guaranteed to cross both a STOPPED period
    # and a RUNNING period regardless of the wall-clock `fixed_start_time` used.
    for _ in range(7200):
        tick = engine.step()
        all_readings.extend(tick.readings)

        reservoir_l = engine.state.lubrication_system.reservoir.quantity_l
        assert reservoir_l <= prev_reservoir_l + 1e-9, "reservoir quantity must never increase"
        prev_reservoir_l = reservoir_l

        machine = engine.state.machine
        if machine.operating_state == OperatingState.STOPPED:
            saw_stopped = True
            assert machine.rpm == 0.0
        elif machine.operating_state.is_running:
            saw_running = True
            assert machine.rpm > 0.0

        cycle = engine.state.lubrication_system.cycle
        if cycle.phase == CyclePhase.IDLE:
            assert engine.state.lubrication_system.pump.is_on is False
        if cycle.phase == CyclePhase.FLOW_DELIVERY:
            saw_flow_delivery = True
        else:
            for circuit_state in engine.state.lubrication_system.circuits.values():
                assert circuit_state.flow_cm3_min == 0.0

        for bearing_state in engine.state.bearings.values():
            assert bearing_state.temperature_c > -50.0
            assert bearing_state.vibration_rms_mm_s >= 0.0
            assert 0.0 <= bearing_state.health <= 1.0
            assert 0.0 <= bearing_state.lubrication_effectiveness <= 1.0

    assert saw_running, "a 2-hour run spanning a configured shift window must include RUNNING time"
    assert saw_stopped, "a 2-hour run must also include STOPPED time (outside the shift window)"
    assert saw_flow_delivery, "at least one lubrication cycle must have delivered lubricant"
    assert len(all_readings) > 0

    for reading in all_readings:
        assert math.isfinite(reading.observed_value)
        assert math.isfinite(reading.true_value)
