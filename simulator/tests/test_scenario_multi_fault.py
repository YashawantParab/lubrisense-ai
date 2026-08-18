"""Multi-fault support (Phase 4 brief §16): at minimum, restriction+sensor drift,
low-reservoir+network-failure, and bearing-issue+sensor-dropout must be able to run
simultaneously without conflict, each still producing its own distinct, attributable effect.
"""

from __future__ import annotations

from simulator.domain.enums import SensorQuality
from simulator.engine.simulation_engine import SimulationEngine
from simulator.scenarios import create_instance, load_scenario_definition


def _instance(name, topology, **kwargs):  # type: ignore[no-untyped-def]
    return create_instance(load_scenario_definition(name), topology, **kwargs)


def test_restriction_and_sensor_drift_coexist(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    restriction = _instance(
        "gradual_restriction", flagship_topology, instance_id="restriction", severity_max=1.0
    )
    drift = _instance("sensor_drift", flagship_topology, instance_id="drift", severity_max=1.0)
    engine = SimulationEngine(
        topology=flagship_topology,
        config=engineering_config,
        seed=61,
        start_time=fixed_start_time,
        step_seconds=15.0,
        scenario_instances=[restriction, drift],
    )
    drifted_sensor_biases = []
    for _ in range(4000):
        tick = engine.step()
        for r in tick.readings:
            if r.sensor_id == drift.target_id and r.observed_value is not None:
                drifted_sensor_biases.append(r.observed_value - r.true_value)

    assert restriction.severity > 0.0
    assert drift.severity > 0.0
    # Restriction's own ground-truth effect is present ...
    circuit_gt = engine.state.lubrication_system.circuits[restriction.target_id]
    assert circuit_gt.restriction_factor > engineering_config.circuit.default_restriction_factor
    # ... at the same time as drift's independent effect on its own sensor.
    assert abs(drifted_sensor_biases[-1]) > abs(drifted_sensor_biases[0])


def test_low_reservoir_and_network_failure_coexist(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    low_reservoir = _instance(
        "low_reservoir", flagship_topology, instance_id="low_res", severity_max=1.0
    )
    network = _instance(
        "network_failure",
        flagship_topology,
        instance_id="network",
        severity_max=1.0,
        target=str(flagship_topology.id),
    )
    engine = SimulationEngine(
        topology=flagship_topology,
        config=engineering_config,
        seed=62,
        start_time=fixed_start_time,
        step_seconds=5.0,
        scenario_instances=[low_reservoir, network],
    )
    saw_comm_loss = False
    for _ in range(1500):
        tick = engine.step()
        for r in tick.readings:
            if r.quality == SensorQuality.COMMUNICATION_LOSS.value:
                saw_comm_loss = True

    assert engine.state.lubrication_system.reservoir.quantity_l < 1.0  # started near-empty
    assert saw_comm_loss


def test_bearing_issue_and_sensor_dropout_coexist(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    bearing_fault = _instance(
        "independent_bearing_fault",
        flagship_topology,
        instance_id="bearing_fault",
        severity_max=1.0,
    )
    dropout = _instance(
        "sensor_dropout", flagship_topology, instance_id="dropout", severity_max=1.0
    )
    engine = SimulationEngine(
        topology=flagship_topology,
        config=engineering_config,
        seed=63,
        start_time=fixed_start_time,
        step_seconds=15.0,
        scenario_instances=[bearing_fault, dropout],
    )
    saw_missing = False
    for _ in range(3000):
        tick = engine.step()
        for r in tick.readings:
            if r.sensor_id == dropout.target_id and r.quality == SensorQuality.MISSING.value:
                saw_missing = True

    assert bearing_fault.severity > 0.0
    assert engine.state.bearings[bearing_fault.target_id].health < 1.0
    assert saw_missing


def test_three_simultaneous_scenarios_do_not_crash_or_corrupt_state(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    instances = [
        _instance("gradual_restriction", flagship_topology, instance_id="r", severity_max=0.6),
        _instance("sensor_drift", flagship_topology, instance_id="d", severity_max=0.5),
        _instance(
            "independent_bearing_fault", flagship_topology, instance_id="b", severity_max=0.5
        ),
    ]
    engine = SimulationEngine(
        topology=flagship_topology,
        config=engineering_config,
        seed=64,
        start_time=fixed_start_time,
        step_seconds=15.0,
        scenario_instances=instances,
    )
    for _ in range(2000):
        engine.step()  # must not raise SimulationInvariantError
    for instance in instances:
        assert instance.severity > 0.0
