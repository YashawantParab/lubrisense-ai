from __future__ import annotations

import uuid

import pytest

from simulator.scenarios.definition import LifecycleSpec, ProgressionSpec, ScenarioDefinition
from simulator.scenarios.effects import build_effects
from simulator.scenarios.instance import ScenarioInstance
from simulator.scenarios.types import (
    ProgressionType,
    ScenarioLifecycleState,
    ScenarioTargetType,
    ScenarioType,
)
from tests.factories import make_topology


def _definition(
    scenario_type: ScenarioType, target_type: ScenarioTargetType, **effect_params: float
) -> ScenarioDefinition:
    return ScenarioDefinition(
        name=f"test_{scenario_type.value.lower()}",
        scenario_type=scenario_type,
        target_type=target_type,
        description="unit test",
        progression=ProgressionSpec(type=ProgressionType.LINEAR, onset_seconds=100.0),
        lifecycle=LifecycleSpec(developing_threshold=0.1, severe_threshold=0.8),
        effect_params=effect_params,
    )


def _active_instance(
    definition: ScenarioDefinition, target_id: uuid.UUID, severity: float, instance_id: str = "i1"
) -> ScenarioInstance:
    instance = ScenarioInstance(
        instance_id=instance_id,
        definition=definition,
        target_id=target_id,
        start_seconds=0.0,
        severity_max=1.0,
    )
    instance.severity = severity
    instance.lifecycle_state = ScenarioLifecycleState.ACTIVE
    return instance


def test_restriction_and_leakage_on_same_circuit_compose_independently(engineering_config) -> None:  # type: ignore[no-untyped-def]
    topology = make_topology()
    circuit_id = topology.lubrication_system.circuits[0].id
    restriction = _active_instance(
        _definition(
            ScenarioType.GRADUAL_RESTRICTION, ScenarioTargetType.CIRCUIT, max_restriction_factor=0.5
        ),
        circuit_id,
        severity=0.5,
        instance_id="restriction",
    )
    leakage = _active_instance(
        _definition(ScenarioType.LEAKAGE, ScenarioTargetType.CIRCUIT, max_leakage_factor=0.4),
        circuit_id,
        severity=0.5,
        instance_id="leak",
    )
    effects = build_effects([restriction, leakage], topology, engineering_config, set())
    assert effects.circuit_restriction_offset[circuit_id] == pytest.approx(0.25)  # 0.5 * 0.5
    assert effects.circuit_leakage_offset[circuit_id] == pytest.approx(0.2)  # 0.5 * 0.4


def test_two_restriction_type_instances_on_same_circuit_sum(engineering_config) -> None:  # type: ignore[no-untyped-def]
    topology = make_topology()
    circuit_id = topology.lubrication_system.circuits[0].id
    a = _active_instance(
        _definition(
            ScenarioType.GRADUAL_RESTRICTION, ScenarioTargetType.CIRCUIT, max_restriction_factor=0.3
        ),
        circuit_id,
        severity=1.0,
        instance_id="a",
    )
    b = _active_instance(
        _definition(
            ScenarioType.SUDDEN_BLOCKAGE, ScenarioTargetType.CIRCUIT, max_restriction_factor=0.2
        ),
        circuit_id,
        severity=1.0,
        instance_id="b",
    )
    effects = build_effects([a, b], topology, engineering_config, set())
    assert effects.circuit_restriction_offset[circuit_id] == pytest.approx(0.5)  # 0.3 + 0.2


def test_network_failure_outranks_sensor_dropout_and_drift(engineering_config) -> None:  # type: ignore[no-untyped-def]
    """docs/SCENARIO_ENGINE.md §6 precedence — network failure affects the whole machine
    regardless of any per-sensor state; this test only verifies the *machine-level* flag is
    set (the engine, not build_effects, applies the actual precedence when collecting
    readings — see test_scenario_quality_semantics.py for that)."""
    topology = make_topology()
    network = _active_instance(
        _definition(ScenarioType.NETWORK_FAILURE, ScenarioTargetType.MACHINE),
        topology.id,
        severity=1.0,
        instance_id="net",
    )
    effects = build_effects([network], topology, engineering_config, set())
    assert topology.id in effects.network_loss_machines


def test_pump_degradation_resolves_to_lubrication_system_id(engineering_config) -> None:  # type: ignore[no-untyped-def]
    topology = make_topology()
    pump_id = topology.lubrication_system.pump.id
    instance = _active_instance(
        _definition(
            ScenarioType.PUMP_DEGRADATION, ScenarioTargetType.PUMP, max_efficiency_loss=0.4
        ),
        pump_id,
        severity=1.0,
    )
    effects = build_effects([instance], topology, engineering_config, set())
    assert effects.pump_efficiency_offset[topology.lubrication_system.id] == pytest.approx(0.4)


def test_independent_bearing_fault_uses_minimum_target_health_across_instances(
    engineering_config,
) -> None:  # type: ignore[no-untyped-def]
    topology = make_topology()
    bearing_id = topology.bearings[0].id
    mild = _active_instance(
        _definition(
            ScenarioType.INDEPENDENT_BEARING_FAULT, ScenarioTargetType.BEARING, max_health_loss=0.3
        ),
        bearing_id,
        severity=1.0,
        instance_id="mild",
    )
    severe = _active_instance(
        _definition(
            ScenarioType.INDEPENDENT_BEARING_FAULT, ScenarioTargetType.BEARING, max_health_loss=0.8
        ),
        bearing_id,
        severity=1.0,
        instance_id="severe",
    )
    effects = build_effects([mild, severe], topology, engineering_config, set())
    # target_health = 1 - severity*max_loss; the *lower* target (more severe fault) wins.
    assert effects.bearing_wear_target_health[bearing_id] == pytest.approx(0.2)


def test_sensor_drift_uses_range_fraction_and_base_bias(engineering_config) -> None:  # type: ignore[no-untyped-def]
    topology = make_topology()
    sensor = next(s for s in topology.sensors if s.sensor_type == "PRESSURE")
    definition = _definition(
        ScenarioType.SENSOR_DRIFT,
        ScenarioTargetType.SENSOR,
        max_bias_fraction_of_range=0.1,
        sign=1.0,
    )
    instance = _active_instance(definition, sensor.id, severity=1.0)
    instance.drift_base_bias = 0.02
    effects = build_effects([instance], topology, engineering_config, set())

    pressure_range = engineering_config.sensors["PRESSURE"].valid_range
    span = pressure_range[1] - pressure_range[0]
    assert effects.sensor_drift_bias[sensor.id] == pytest.approx(0.02 + 0.1 * span)


def test_inactive_instance_produces_no_effect(engineering_config) -> None:  # type: ignore[no-untyped-def]
    topology = make_topology()
    circuit_id = topology.lubrication_system.circuits[0].id
    instance = _active_instance(
        _definition(
            ScenarioType.GRADUAL_RESTRICTION, ScenarioTargetType.CIRCUIT, max_restriction_factor=0.5
        ),
        circuit_id,
        severity=0.5,
    )
    instance.lifecycle_state = ScenarioLifecycleState.SCHEDULED  # not active
    effects = build_effects([instance], topology, engineering_config, set())
    assert circuit_id not in effects.circuit_restriction_offset


def test_low_reservoir_only_fires_on_activation_edge(engineering_config) -> None:  # type: ignore[no-untyped-def]
    topology = make_topology()
    reservoir_id = topology.lubrication_system.reservoir.id
    instance = _active_instance(
        _definition(
            ScenarioType.LOW_RESERVOIR, ScenarioTargetType.RESERVOIR, min_target_level_percent=5.0
        ),
        reservoir_id,
        severity=1.0,
    )
    effects_no_edge = build_effects([instance], topology, engineering_config, set())
    assert reservoir_id not in effects_no_edge.low_reservoir_targets

    effects_with_edge = build_effects(
        [instance], topology, engineering_config, {instance.instance_id}
    )
    assert effects_with_edge.low_reservoir_targets[reservoir_id] == pytest.approx(5.0)
