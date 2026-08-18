from __future__ import annotations

import uuid

import pytest

from simulator.scenarios.targeting import ScenarioTargetError, resolve_target
from simulator.scenarios.types import ScenarioTargetType
from tests.factories import make_topology


def test_resolve_default_target_when_none_given() -> None:
    topology = make_topology()
    target = resolve_target(topology, ScenarioTargetType.CIRCUIT)
    assert target == topology.lubrication_system.circuits[0].id


def test_resolve_by_code() -> None:
    topology = make_topology()
    second_circuit = topology.lubrication_system.circuits[1]
    target = resolve_target(topology, ScenarioTargetType.CIRCUIT, second_circuit.code)
    assert target == second_circuit.id


def test_resolve_by_uuid_string() -> None:
    topology = make_topology()
    bearing = topology.bearings[0]
    target = resolve_target(topology, ScenarioTargetType.BEARING, str(bearing.id))
    assert target == bearing.id


def test_resolve_machine_target() -> None:
    topology = make_topology()
    target = resolve_target(topology, ScenarioTargetType.MACHINE)
    assert target == topology.id


def test_resolve_sensor_target_by_code() -> None:
    topology = make_topology()
    sensor = topology.sensors[0]
    target = resolve_target(topology, ScenarioTargetType.SENSOR, sensor.sensor_code)
    assert target == sensor.id


def test_unknown_code_raises() -> None:
    topology = make_topology()
    with pytest.raises(ScenarioTargetError):
        resolve_target(topology, ScenarioTargetType.CIRCUIT, "NOT-A-REAL-CIRCUIT")


def test_random_uuid_not_on_machine_raises() -> None:
    topology = make_topology()
    with pytest.raises(ScenarioTargetError):
        resolve_target(topology, ScenarioTargetType.BEARING, str(uuid.uuid4()))


def test_wrong_entity_type_id_raises() -> None:
    """A real id that exists on the machine, but of the wrong entity type, must fail —
    Phase 4 brief §17: "invalid or incompatible target types must fail validation"."""
    topology = make_topology()
    circuit_id = topology.lubrication_system.circuits[0].id
    with pytest.raises(ScenarioTargetError):
        resolve_target(topology, ScenarioTargetType.BEARING, str(circuit_id))


def test_no_candidates_raises() -> None:
    topology = make_topology(num_bearings=0, sensor_types=())
    with pytest.raises(ScenarioTargetError):
        resolve_target(topology, ScenarioTargetType.BEARING)
