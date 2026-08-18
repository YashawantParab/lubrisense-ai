"""Extended-run numerical stability (Phase 3 brief §24): several simulated days at a
larger step size, asserting no NaN/inf/impossible-negative values occur — `step()` itself
raises `SimulationInvariantError` the instant such a value appears (see
`SimulationEngine._validate_state`), so simply completing the run without an exception is
the pass condition. Also checks pump efficiency / reservoir level stay within sane bounds
across many repeated lubrication cycles.
"""

from __future__ import annotations

from simulator.engine.simulation_engine import SimulationEngine


def test_seven_day_run_has_no_numerical_instability(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    engine = SimulationEngine(
        topology=flagship_topology,
        config=engineering_config,
        seed=2024,
        start_time=fixed_start_time,
        step_seconds=60.0,  # 1-minute step keeps a 7-day run to a few thousand ticks
    )

    ticks = int(7 * 24 * 3600 / engine.step_seconds)
    max_pressure_seen = 0.0
    min_efficiency_seen = 1.0

    for _ in range(ticks):
        engine.step()
        ls = engine.state.lubrication_system
        max_pressure_seen = max(max_pressure_seen, ls.pump.pressure_bar)
        min_efficiency_seen = min(min_efficiency_seen, ls.pump.efficiency)

    assert max_pressure_seen <= engineering_config.pump.max_pressure_bar
    assert 0.5 <= min_efficiency_seen <= 1.0
    assert engine.state.lubrication_system.reservoir.quantity_l >= 0.0
    for bearing_state in engine.state.bearings.values():
        assert 0.0 <= bearing_state.health <= 1.0
        assert 0.0 <= bearing_state.lubrication_effectiveness <= 1.0
