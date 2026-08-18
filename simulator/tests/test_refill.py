"""Refill event tests (Phase 4 brief §24): a synthetic operational event, not a failure
mode — supports Low Reservoir recovery, works standalone with zero scenarios active, and
the observed RESERVOIR_LEVEL sensor responds to it through the existing sensor model (not a
special-cased sensor value)."""

from __future__ import annotations

from simulator.engine.simulation_engine import SimulationEngine
from simulator.physics import reservoir as reservoir_physics
from simulator.scenarios.scheduler import AutoRefillPolicy


def test_refill_increases_true_reservoir_quantity(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    engine = SimulationEngine(
        topology=flagship_topology,
        config=engineering_config,
        seed=71,
        start_time=fixed_start_time,
        step_seconds=15.0,
        refill_policy=AutoRefillPolicy(threshold_percent=90.0, to_percent=100.0, delay_seconds=0.0),
    )
    # force the reservoir low so the policy triggers almost immediately
    reservoir_physics.refill(engine.state.lubrication_system.reservoir, to_percent=50.0)
    quantity_before = engine.state.lubrication_system.reservoir.quantity_l

    saw_refill_event = False
    for _ in range(5):
        tick = engine.step()
        if tick.ground_truth.refill_event:
            saw_refill_event = True

    assert saw_refill_event
    assert engine.state.lubrication_system.reservoir.quantity_l > quantity_before


def test_refill_is_recorded_in_ground_truth_only_on_the_triggering_tick(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    engine = SimulationEngine(
        topology=flagship_topology,
        config=engineering_config,
        seed=72,
        start_time=fixed_start_time,
        step_seconds=15.0,
        refill_policy=AutoRefillPolicy(threshold_percent=90.0, to_percent=100.0, delay_seconds=0.0),
    )
    reservoir_physics.refill(engine.state.lubrication_system.reservoir, to_percent=50.0)

    refill_tick_count = 0
    for _ in range(10):
        tick = engine.step()
        if tick.ground_truth.refill_event:
            refill_tick_count += 1

    assert refill_tick_count == 1  # refilled once, then stays above threshold


def test_refill_causes_observed_reservoir_level_to_respond_through_sensor_model(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    """Directly triggers `reservoir.refill()` mid-run (bypassing the AutoRefillPolicy
    entirely) so the "before" window is captured at the low level, uncontaminated by the
    refill — isolates only "does the sensor respond to a refill through the normal
    observation pathway," not the policy's own trigger timing (covered separately above)."""
    engine = SimulationEngine(
        topology=flagship_topology,
        config=engineering_config,
        seed=73,
        start_time=fixed_start_time,
        step_seconds=15.0,
        refill_policy=None,
    )
    reservoir_physics.refill(engine.state.lubrication_system.reservoir, to_percent=20.0)

    levels_before = []
    for _ in range(2):
        tick = engine.step()
        for r in tick.readings:
            if r.measurement_type == "RESERVOIR_LEVEL":
                levels_before.append(r.observed_value)

    reservoir_physics.refill(engine.state.lubrication_system.reservoir, to_percent=100.0)

    levels_after = []
    for _ in range(2):
        tick = engine.step()
        for r in tick.readings:
            if r.measurement_type == "RESERVOIR_LEVEL":
                levels_after.append(r.observed_value)

    assert levels_after[-1] > levels_before[0] + 30  # unmistakably higher, not just noise


def test_no_refill_policy_reservoir_never_refills(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    engine = SimulationEngine(
        topology=flagship_topology,
        config=engineering_config,
        seed=74,
        start_time=fixed_start_time,
        step_seconds=15.0,
        refill_policy=None,
    )
    reservoir_physics.refill(engine.state.lubrication_system.reservoir, to_percent=5.0)
    prev = engine.state.lubrication_system.reservoir.quantity_l
    for _ in range(500):
        tick = engine.step()
        assert tick.ground_truth.refill_event is False
        assert engine.state.lubrication_system.reservoir.quantity_l <= prev + 1e-9
        prev = engine.state.lubrication_system.reservoir.quantity_l
