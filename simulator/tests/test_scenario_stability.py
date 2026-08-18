"""Extended-run numerical stability with an active failure scenario (Phase 4 brief §37):
several simulated days at a larger step size, with Gradual Restriction driving toward full
severity and staying there — the scenario that pushes hidden state furthest from its
healthy defaults. `SimulationEngine.step()` raises `SimulationInvariantError` on any NaN/
inf/impossible-negative value, so completing the run without an exception is the pass
condition (matches tests/test_stability.py's Phase 3 healthy-run methodology)."""

from __future__ import annotations

import math

from simulator.engine.simulation_engine import SimulationEngine
from simulator.scenarios import create_instance, load_scenario_definition


def test_seven_day_run_with_gradual_restriction_has_no_numerical_instability(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    definition = load_scenario_definition("gradual_restriction")
    instance = create_instance(definition, flagship_topology, start_seconds=0.0, severity_max=1.0)
    engine = SimulationEngine(
        topology=flagship_topology,
        config=engineering_config,
        seed=2024,
        start_time=fixed_start_time,
        step_seconds=60.0,
        scenario_instances=[instance],
    )

    ticks = int(7 * 24 * 3600 / engine.step_seconds)
    max_pressure_seen = 0.0
    min_health_seen = 1.0

    for _ in range(ticks):
        tick = engine.step()
        ls = engine.state.lubrication_system
        max_pressure_seen = max(max_pressure_seen, ls.pump.pressure_bar)
        for b in engine.state.bearings.values():
            min_health_seen = min(min_health_seen, b.health)
        for reading in tick.readings:
            assert math.isfinite(reading.true_value)
            if reading.observed_value is not None:
                assert math.isfinite(reading.observed_value)

    assert instance.severity > 0.9  # scenario reached (near-)full severity over 7 days
    assert max_pressure_seen <= engineering_config.pump.max_pressure_bar
    assert 0.0 <= min_health_seen <= 1.0
    assert engine.state.lubrication_system.reservoir.quantity_l >= 0.0


def test_seven_day_run_with_multi_fault_has_no_numerical_instability(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    instances = [
        create_instance(
            load_scenario_definition("leakage"),
            flagship_topology,
            instance_id="l",
            severity_max=1.0,
        ),
        create_instance(
            load_scenario_definition("sensor_drift"),
            flagship_topology,
            instance_id="d",
            severity_max=1.0,
        ),
        create_instance(
            load_scenario_definition("independent_bearing_fault"),
            flagship_topology,
            instance_id="b",
            severity_max=1.0,
        ),
    ]
    engine = SimulationEngine(
        topology=flagship_topology,
        config=engineering_config,
        seed=2025,
        start_time=fixed_start_time,
        step_seconds=60.0,
        scenario_instances=instances,
    )
    ticks = int(7 * 24 * 3600 / engine.step_seconds)
    for _ in range(ticks):
        tick = engine.step()
        for reading in tick.readings:
            assert math.isfinite(reading.true_value)
    for instance in instances:
        assert instance.severity > 0.0
