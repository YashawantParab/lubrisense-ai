from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.asset_hierarchy_service import AssetHierarchyService
from app.services.machine_service import MachineService
from tests.factories import (
    make_bearing,
    make_circuit,
    make_customer,
    make_lubrication_point,
    make_lubrication_system,
    make_machine,
    make_plant,
    make_production_line,
    make_sensor,
    make_site,
    make_tenant,
)


@pytest.mark.asyncio
async def test_full_hierarchy_returns_correct_tree(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    customer = await make_customer(db_session, tenant)
    site = await make_site(db_session, tenant, customer)
    plant = await make_plant(db_session, tenant, site)
    line = await make_production_line(db_session, tenant, plant)
    machine = await make_machine(db_session, tenant, line)

    service = AssetHierarchyService(db_session)
    customers = await service.get_full_hierarchy(tenant.id)

    assert [c.id for c in customers] == [customer.id]
    assert [s.id for s in customers[0].sites] == [site.id]
    assert [p.id for p in customers[0].sites[0].plants] == [plant.id]
    assert [pl.id for pl in customers[0].sites[0].plants[0].production_lines] == [line.id]
    assert [m.id for m in customers[0].sites[0].plants[0].production_lines[0].machines] == [
        machine.id
    ]


@pytest.mark.asyncio
async def test_machine_hierarchy_resolves_bearings_lubrication_and_sensors(
    db_session: AsyncSession,
) -> None:
    tenant = await make_tenant(db_session)
    customer = await make_customer(db_session, tenant)
    site = await make_site(db_session, tenant, customer)
    plant = await make_plant(db_session, tenant, site)
    line = await make_production_line(db_session, tenant, plant)
    machine = await make_machine(db_session, tenant, line)

    bearing_1 = await make_bearing(db_session, tenant, machine)
    bearing_2 = await make_bearing(db_session, tenant, machine)

    system = await make_lubrication_system(db_session, tenant, machine)
    circuit = await make_circuit(db_session, tenant, system)
    point_1 = await make_lubrication_point(db_session, tenant, circuit, bearing_1)
    point_2 = await make_lubrication_point(db_session, tenant, circuit, bearing_2)

    machine_sensor = await make_sensor(db_session, tenant, machine_id=machine.id)
    bearing_sensor = await make_sensor(db_session, tenant, bearing_id=bearing_1.id)
    circuit_sensor = await make_sensor(db_session, tenant, circuit_id=circuit.id)
    system_sensor = await make_sensor(db_session, tenant, lubrication_system_id=system.id)

    service = MachineService(db_session)
    hierarchy = await service.get_hierarchy(tenant.id, machine.id)

    assert hierarchy.machine.id == machine.id
    assert {b.id for b in hierarchy.bearings} == {bearing_1.id, bearing_2.id}
    assert [ls.id for ls in hierarchy.lubrication_systems] == [system.id]
    assert hierarchy.lubrication_systems[0].circuits[0].id == circuit.id

    point_ids = {p.id for p in hierarchy.lubrication_systems[0].circuits[0].lubrication_points}
    assert point_ids == {point_1.id, point_2.id}

    sensor_ids = {s.id for s in hierarchy.sensors}
    assert sensor_ids == {machine_sensor.id, bearing_sensor.id, circuit_sensor.id, system_sensor.id}
