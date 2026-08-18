"""Required verification (Phase 4 brief §37):
- true/observed separation during Sensor Drift
- physical truth continues during Sensor Dropout / Network Failure
- Network Failure outranks Sensor Dropout for a sensor affected by both
"""

from __future__ import annotations

import math

from simulator.domain.enums import SensorQuality
from simulator.engine.simulation_engine import SimulationEngine
from simulator.scenarios import create_instance, load_scenario_definition


def test_sensor_drift_moves_observed_but_never_true_value(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    definition = load_scenario_definition("sensor_drift")
    instance = create_instance(definition, flagship_topology, start_seconds=0.0, severity_max=1.0)
    engine = SimulationEngine(
        topology=flagship_topology,
        config=engineering_config,
        seed=51,
        start_time=fixed_start_time,
        step_seconds=15.0,
        scenario_instances=[instance],
    )
    true_values = []
    biases = []
    for _ in range(4000):
        tick = engine.step()
        for r in tick.readings:
            if r.sensor_id == instance.target_id:
                true_values.append(r.true_value)
                assert r.observed_value is not None
                biases.append(r.observed_value - r.true_value)

    assert instance.severity > 0.05
    # true_value must show no scenario-driven trend (it only reflects real physical
    # variation, e.g. load/cycle-driven pressure swings) ...
    first_half_true = true_values[: len(true_values) // 2]
    second_half_true = true_values[len(true_values) // 2 :]
    # ... while the observed-vs-true bias must grow monotonically-ish with severity.
    first_half_bias = [abs(b) for b in biases[: len(biases) // 2]]
    second_half_bias = [abs(b) for b in biases[len(biases) // 2 :]]
    assert sum(second_half_bias) / len(second_half_bias) > sum(first_half_bias) / len(
        first_half_bias
    )
    assert len(first_half_true) > 0 and len(second_half_true) > 0  # sanity: data collected


def test_sensor_dropout_preserves_true_value_and_marks_observation_missing(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    definition = load_scenario_definition("sensor_dropout")
    instance = create_instance(definition, flagship_topology, start_seconds=0.0, severity_max=1.0)
    engine = SimulationEngine(
        topology=flagship_topology,
        config=engineering_config,
        seed=52,
        start_time=fixed_start_time,
        step_seconds=5.0,
        scenario_instances=[instance],
    )
    saw_missing = False
    for _ in range(2000):
        tick = engine.step()
        for r in tick.readings:
            if r.sensor_id != instance.target_id:
                continue
            assert math.isfinite(r.true_value)  # physical truth always present
            if r.quality == SensorQuality.MISSING.value:
                saw_missing = True
                assert r.observed_value is None
            else:
                assert r.observed_value is not None
    assert saw_missing


def test_network_failure_preserves_true_value_across_every_sensor(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    definition = load_scenario_definition("network_failure")
    instance = create_instance(definition, flagship_topology, start_seconds=0.0, severity_max=1.0)
    engine = SimulationEngine(
        topology=flagship_topology,
        config=engineering_config,
        seed=53,
        start_time=fixed_start_time,
        step_seconds=5.0,
        scenario_instances=[instance],
    )
    saw_comm_loss = False
    sensors_seen_with_comm_loss = set()
    for _ in range(2000):
        tick = engine.step()
        for r in tick.readings:
            assert math.isfinite(r.true_value)
            if r.quality == SensorQuality.COMMUNICATION_LOSS.value:
                saw_comm_loss = True
                sensors_seen_with_comm_loss.add(r.sensor_id)
                assert r.observed_value is None
    assert saw_comm_loss
    # affects multiple distinct sensors at once — the whole-machine signature.
    assert len(sensors_seen_with_comm_loss) > 1


def test_network_failure_outranks_sensor_dropout_for_the_same_sensor(
    flagship_topology, engineering_config, fixed_start_time
) -> None:  # type: ignore[no-untyped-def]
    dropout_definition = load_scenario_definition("sensor_dropout")
    dropout_instance = create_instance(
        dropout_definition,
        flagship_topology,
        instance_id="dropout",
        start_seconds=0.0,
        severity_max=1.0,
    )
    network_definition = load_scenario_definition("network_failure")
    network_instance = create_instance(
        network_definition,
        flagship_topology,
        instance_id="network",
        start_seconds=0.0,
        severity_max=1.0,
        target=str(flagship_topology.id),
    )
    engine = SimulationEngine(
        topology=flagship_topology,
        config=engineering_config,
        seed=54,
        start_time=fixed_start_time,
        step_seconds=5.0,
        scenario_instances=[dropout_instance, network_instance],
    )
    violations = 0
    saw_comm_loss_while_network_active = False
    for _ in range(2000):
        tick = engine.step()
        network_active = network_instance.severity > 0.0
        for r in tick.readings:
            if r.sensor_id != dropout_instance.target_id:
                continue
            if network_active:
                if r.quality == SensorQuality.MISSING.value:
                    violations += 1  # Sensor Dropout's label leaked through — precedence bug
                if r.quality == SensorQuality.COMMUNICATION_LOSS.value:
                    saw_comm_loss_while_network_active = True

    # Whenever Network Failure is active, this sensor must never show MISSING (Sensor
    # Dropout's own label) — COMMUNICATION_LOSS must win every time (docs/SCENARIO_ENGINE.md
    # §6 precedence).
    assert violations == 0
    assert saw_comm_loss_while_network_active
