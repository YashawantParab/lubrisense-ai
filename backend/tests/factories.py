"""Minimal hierarchy-building helpers for tests.

Every helper takes an `AsyncSession` and returns a persisted-but-unflushed-to-others
(flushed to get an id, never committed) ORM object, so tests using the `db_session`
fixture can build exactly the slice of the hierarchy they need without going through the
service layer (which is what app/services tests are for) or duplicating boilerplate.

Names/codes are randomized per call (`uuid.uuid4().hex[:8]`) so tests can run repeatedly
against the same database without unique-constraint collisions, even though nothing here
is ever committed.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import (
    CommercialStatus,
    CommissioningState,
    Criticality,
    LubricationSystemType,
    MachineStatus,
    MachineType,
    OperationalStatus,
    SensorQualityState,
    SensorStatus,
    SensorType,
    ServiceTier,
    TenantStatus,
)
from app.domain.models import (
    Bearing,
    Circuit,
    CustomerAccount,
    Gateway,
    LubricationPoint,
    LubricationSystem,
    Machine,
    Plant,
    ProductionLine,
    Sensor,
    Site,
    Tenant,
)


def unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def make_tenant(session: AsyncSession) -> Tenant:
    tenant = Tenant(
        name=unique("Test Tenant"), slug=unique("test-tenant"), status=TenantStatus.ACTIVE
    )
    session.add(tenant)
    await session.flush()
    return tenant


async def make_customer(session: AsyncSession, tenant: Tenant) -> CustomerAccount:
    customer = CustomerAccount(
        tenant_id=tenant.id,
        name=unique("Test Customer"),
        code=unique("CUST"),
        service_tier=ServiceTier.CONNECTED_MONITORING,
        commercial_status=CommercialStatus.ACTIVE,
        metadata_={},
    )
    session.add(customer)
    await session.flush()
    return customer


async def make_site(session: AsyncSession, tenant: Tenant, customer: CustomerAccount) -> Site:
    site = Site(
        tenant_id=tenant.id,
        customer_account_id=customer.id,
        name=unique("Test Site"),
        code=unique("SITE"),
        status=OperationalStatus.ACTIVE,
        metadata_={},
    )
    session.add(site)
    await session.flush()
    return site


async def make_plant(session: AsyncSession, tenant: Tenant, site: Site) -> Plant:
    plant = Plant(
        tenant_id=tenant.id,
        site_id=site.id,
        name=unique("Test Plant"),
        code=unique("PLANT"),
        status=OperationalStatus.ACTIVE,
        metadata_={},
    )
    session.add(plant)
    await session.flush()
    return plant


async def make_production_line(
    session: AsyncSession, tenant: Tenant, plant: Plant
) -> ProductionLine:
    line = ProductionLine(
        tenant_id=tenant.id,
        plant_id=plant.id,
        name=unique("Test Line"),
        code=unique("LINE"),
        status=OperationalStatus.ACTIVE,
        criticality=Criticality.MEDIUM,
        metadata_={},
    )
    session.add(line)
    await session.flush()
    return line


async def make_machine(session: AsyncSession, tenant: Tenant, line: ProductionLine) -> Machine:
    machine = Machine(
        tenant_id=tenant.id,
        production_line_id=line.id,
        name=unique("Test Machine"),
        asset_code=unique("ASSET"),
        machine_type=MachineType.MOTOR,
        criticality=Criticality.MEDIUM,
        status=MachineStatus.MONITORED,
        operating_profile={},
        metadata_={},
    )
    session.add(machine)
    await session.flush()
    return machine


async def make_bearing(session: AsyncSession, tenant: Tenant, machine: Machine) -> Bearing:
    bearing = Bearing(
        tenant_id=tenant.id,
        machine_id=machine.id,
        name=unique("Test Bearing"),
        position=unique("POS"),
        criticality=Criticality.MEDIUM,
        status=OperationalStatus.ACTIVE,
        metadata_={},
    )
    session.add(bearing)
    await session.flush()
    return bearing


async def make_lubrication_system(
    session: AsyncSession, tenant: Tenant, machine: Machine
) -> LubricationSystem:
    system = LubricationSystem(
        tenant_id=tenant.id,
        machine_id=machine.id,
        name=unique("Test Lube System"),
        system_type=LubricationSystemType.PROGRESSIVE,
        status=OperationalStatus.ACTIVE,
        commissioning_state=CommissioningState.COMMISSIONED,
        configuration_version="v1",
        metadata_={},
    )
    session.add(system)
    await session.flush()
    return system


async def make_circuit(session: AsyncSession, tenant: Tenant, system: LubricationSystem) -> Circuit:
    circuit = Circuit(
        tenant_id=tenant.id,
        lubrication_system_id=system.id,
        name=unique("Test Circuit"),
        code=unique("CIRC"),
        status=OperationalStatus.ACTIVE,
        metadata_={},
    )
    session.add(circuit)
    await session.flush()
    return circuit


async def make_lubrication_point(
    session: AsyncSession, tenant: Tenant, circuit: Circuit, bearing: Bearing | None
) -> LubricationPoint:
    point = LubricationPoint(
        tenant_id=tenant.id,
        circuit_id=circuit.id,
        bearing_id=bearing.id if bearing else None,
        name=unique("Test Point"),
        code=unique("LP"),
        status=OperationalStatus.ACTIVE,
        metadata_={},
    )
    session.add(point)
    await session.flush()
    return point


async def make_sensor(
    session: AsyncSession,
    tenant: Tenant,
    sensor_type: SensorType = SensorType.VIBRATION_RMS,
    **attachment: object,
) -> Sensor:
    sensor = Sensor(
        tenant_id=tenant.id,
        sensor_code=unique("SENSOR"),
        name=unique("Test Sensor"),
        sensor_type=sensor_type,
        status=SensorStatus.ACTIVE,
        quality_state=SensorQualityState.UNKNOWN,
        metadata_={},
        **attachment,
    )
    session.add(sensor)
    await session.flush()
    return sensor


async def make_gateway(session: AsyncSession, tenant: Tenant, **attachment: object) -> Gateway:
    gateway = Gateway(
        tenant_id=tenant.id,
        gateway_code=unique("GW"),
        name=unique("Test Gateway"),
        status=OperationalStatus.ACTIVE,
        metadata_={},
        **attachment,
    )
    session.add(gateway)
    await session.flush()
    return gateway
