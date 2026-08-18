"""Synthetic `MachineTopology` builders for tests that don't need the live database —
mirrors the shape `simulator.engine.repository.TopologyRepository` would return, with
predictable, deterministic ids."""

from __future__ import annotations

import uuid

from simulator.domain.topology import (
    BearingTopology,
    CircuitTopology,
    ControllerTopology,
    DistributorTopology,
    LubricationPointTopology,
    LubricationSystemTopology,
    MachineTopology,
    PumpTopology,
    ReservoirTopology,
    SensorTopology,
)

TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def make_topology(
    *,
    machine_type: str = "CONVEYOR",
    num_bearings: int = 2,
    num_circuits: int = 2,
    sensor_types: tuple[str, ...] = (
        "PRESSURE",
        "RESERVOIR_LEVEL",
        "PUMP_CURRENT",
        "BEARING_TEMPERATURE",
        "VIBRATION_RMS",
        "RPM",
    ),
) -> MachineTopology:
    machine_id = uuid.uuid4()
    bearings = tuple(
        BearingTopology(
            id=uuid.uuid4(), name=f"Bearing {i}", position=f"POS_{i}", criticality="MEDIUM"
        )
        for i in range(num_bearings)
    )

    reservoir = ReservoirTopology(
        id=uuid.uuid4(), name="Reservoir", capacity_demo=10.0, capacity_unit="L"
    )
    pump = PumpTopology(id=uuid.uuid4(), name="Pump", pump_type="Progressive")
    controller = ControllerTopology(
        id=uuid.uuid4(), name="Controller", controller_type="Timer-based"
    )
    distributor = DistributorTopology(id=uuid.uuid4(), name="Distributor")

    circuits = []
    for i in range(num_circuits):
        bearing = bearings[i % len(bearings)] if bearings else None
        lp = (
            LubricationPointTopology(id=uuid.uuid4(), code=f"LP{i + 1}", bearing_id=bearing.id)
            if bearing
            else None
        )
        circuits.append(
            CircuitTopology(
                id=uuid.uuid4(),
                code=f"C{i + 1}",
                lubrication_points=(lp,) if lp else (),
            )
        )
    circuits_t = tuple(circuits)

    lubrication_system = LubricationSystemTopology(
        id=uuid.uuid4(),
        name="Lubrication System",
        system_type="PROGRESSIVE",
        reservoir=reservoir,
        pump=pump,
        controller=controller,
        distributor=distributor,
        circuits=circuits_t,
    )

    sensors = []
    for st in sensor_types:
        if st == "PRESSURE":
            entity_id, entity_type = circuits_t[0].id, "circuit"
        elif st == "RESERVOIR_LEVEL":
            entity_id, entity_type = reservoir.id, "reservoir"
        elif st == "PUMP_CURRENT":
            entity_id, entity_type = pump.id, "pump"
        elif st in ("BEARING_TEMPERATURE", "VIBRATION_RMS", "VIBRATION_PEAK"):
            entity_id, entity_type = bearings[0].id, "bearing"
        else:
            entity_id, entity_type = machine_id, "machine"
        sensors.append(
            SensorTopology(
                id=uuid.uuid4(),
                sensor_code=f"{st}-{entity_id.hex[:6]}",
                sensor_type=st,
                unit=None,
                attached_entity_type=entity_type,
                attached_entity_id=entity_id,
            )
        )

    return MachineTopology(
        id=machine_id,
        tenant_id=TENANT_ID,
        name="Synthetic Machine",
        asset_code="SYN-001",
        machine_type=machine_type,
        criticality="MEDIUM",
        bearings=bearings,
        lubrication_system=lubrication_system,
        sensors=tuple(sensors),
    )
