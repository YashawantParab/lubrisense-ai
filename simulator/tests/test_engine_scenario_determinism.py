from __future__ import annotations

from simulator.engine.simulation_engine import SimulationEngine
from simulator.scenarios import create_instance, load_scenario_definition


def _run(topology, config, seed, start_time, scenario_name, ticks=1000, step_seconds=5.0):  # type: ignore[no-untyped-def]
    definition = load_scenario_definition(scenario_name)
    instance = create_instance(definition, topology, start_seconds=0.0)
    engine = SimulationEngine(
        topology=topology,
        config=config,
        seed=seed,
        start_time=start_time,
        step_seconds=step_seconds,
        scenario_instances=[instance],
    )
    rows = []
    for _ in range(ticks):
        tick = engine.step()
        for r in tick.readings:
            rows.append(
                (r.sensor_id, r.measurement_type, r.true_value, r.observed_value, r.quality)
            )
        rows.append(("__gt__", instance.severity, instance.lifecycle_state.value))
    return rows


def test_same_seed_same_scenario_is_byte_identical(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    a = _run(flagship_topology, engineering_config, 11, fixed_start_time, "gradual_restriction")
    b = _run(flagship_topology, engineering_config, 11, fixed_start_time, "gradual_restriction")
    assert a == b
    assert len(a) > 0


def test_different_seed_same_scenario_differs_in_noise(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    a = _run(flagship_topology, engineering_config, 1, fixed_start_time, "leakage")
    b = _run(flagship_topology, engineering_config, 2, fixed_start_time, "leakage")
    assert a != b
    assert len(a) == len(b)


def test_intermittent_dropout_scenario_is_still_deterministic(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    a = _run(
        flagship_topology, engineering_config, 5, fixed_start_time, "sensor_dropout", ticks=2000
    )
    b = _run(
        flagship_topology, engineering_config, 5, fixed_start_time, "sensor_dropout", ticks=2000
    )
    assert a == b


def test_network_failure_scenario_is_deterministic(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    a = _run(
        flagship_topology, engineering_config, 9, fixed_start_time, "network_failure", ticks=2000
    )
    b = _run(
        flagship_topology, engineering_config, 9, fixed_start_time, "network_failure", ticks=2000
    )
    assert a == b
