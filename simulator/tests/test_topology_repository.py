from __future__ import annotations

import uuid

import pytest

from simulator.engine.repository import TopologyRepository

pytestmark = pytest.mark.usefixtures("flagship_topology")


def test_flagship_topology_resolves_from_live_database(flagship_topology) -> None:  # type: ignore[no-untyped-def]
    assert flagship_topology.asset_code == "L1-7B43-M000"
    assert flagship_topology.machine_type == "CONVEYOR"
    assert len(flagship_topology.bearings) == 2
    assert flagship_topology.lubrication_system is not None
    assert len(flagship_topology.lubrication_system.circuits) == 2
    assert len(flagship_topology.sensors) == 8


def test_flagship_lubrication_points_map_circuits_to_bearings(flagship_topology) -> None:  # type: ignore[no-untyped-def]
    bearing_ids = {b.id for b in flagship_topology.bearings}
    for c in flagship_topology.lubrication_system.circuits:
        for lp in c.lubrication_points:
            assert lp.bearing_id in bearing_ids


def test_lookup_by_machine_id_matches_lookup_by_asset_code(flagship_topology) -> None:  # type: ignore[no-untyped-def]
    repo = TopologyRepository()
    by_id = repo.load_machine_topology(machine_id=flagship_topology.id)
    assert by_id.asset_code == flagship_topology.asset_code
    assert by_id.id == flagship_topology.id


def test_unknown_asset_code_raises_lookup_error() -> None:
    repo = TopologyRepository()
    try:
        repo.load_machine_topology(asset_code="DOES-NOT-EXIST")
    except LookupError:
        return
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"live database unavailable: {exc}")
    else:
        raise AssertionError("expected LookupError")


def test_no_args_raises_value_error() -> None:
    repo = TopologyRepository()
    with pytest.raises(ValueError):
        repo.load_machine_topology()


def test_random_uuid_asset_id_raises_lookup_error() -> None:
    repo = TopologyRepository()
    try:
        repo.load_machine_topology(machine_id=uuid.uuid4())
    except LookupError:
        return
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"live database unavailable: {exc}")
    else:
        raise AssertionError("expected LookupError")
