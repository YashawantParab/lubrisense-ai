from __future__ import annotations

from simulator.engine.simulation_engine import SimulationEngine


def _run(topology, config, seed: int, start_time, ticks: int = 120, step_seconds: float = 5.0):  # type: ignore[no-untyped-def]
    engine = SimulationEngine(
        topology=topology,
        config=config,
        seed=seed,
        start_time=start_time,
        step_seconds=step_seconds,
    )
    rows = []
    for _ in range(ticks):
        tick = engine.step()
        for r in tick.readings:
            rows.append(
                (r.sensor_id, r.measurement_type, r.true_value, r.observed_value, r.quality)
            )
    return rows


def test_same_seed_produces_identical_output(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    run_a = _run(flagship_topology, engineering_config, seed=42, start_time=fixed_start_time)
    run_b = _run(flagship_topology, engineering_config, seed=42, start_time=fixed_start_time)
    assert run_a == run_b
    assert len(run_a) > 0


def test_different_seed_produces_different_noise_but_similar_shape(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    run_a = _run(flagship_topology, engineering_config, seed=1, start_time=fixed_start_time)
    run_b = _run(flagship_topology, engineering_config, seed=2, start_time=fixed_start_time)
    assert run_a != run_b
    assert len(run_a) == len(run_b)
    # Same set of measurement types observed regardless of seed (equivalent physical
    # behavior, different noise realization — Phase 3 brief §16).
    types_a = {row[1] for row in run_a}
    types_b = {row[1] for row in run_b}
    assert types_a == types_b


def test_determinism_holds_across_a_longer_run(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    run_a = _run(
        flagship_topology, engineering_config, seed=99, start_time=fixed_start_time, ticks=600
    )
    run_b = _run(
        flagship_topology, engineering_config, seed=99, start_time=fixed_start_time, ticks=600
    )
    assert run_a == run_b
