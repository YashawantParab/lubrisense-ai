"""Database-level domain invariants — see app/domain/models.py and
docs/ASSET_HIERARCHY.md. These assert the constraint actually exists in the schema, not
just that application code happens to check it first.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import OperationalStatus
from app.domain.models import Gateway, LubricationPoint, Machine, Sensor, Site
from tests.factories import (
    make_bearing,
    make_circuit,
    make_customer,
    make_lubrication_system,
    make_machine,
    make_plant,
    make_production_line,
    make_site,
    make_tenant,
    unique,
)


@pytest.mark.asyncio
async def test_child_cannot_reference_parent_from_different_tenant(
    db_session: AsyncSession,
) -> None:
    tenant_a = await make_tenant(db_session)
    tenant_b = await make_tenant(db_session)
    customer_b = await make_customer(db_session, tenant_b)

    # A site claiming tenant_a but pointing at a customer that belongs to tenant_b.
    rogue_site = Site(
        tenant_id=tenant_a.id,
        customer_account_id=customer_b.id,
        name="Rogue Site",
        code=unique("SITE"),
        status=OperationalStatus.ACTIVE,
        metadata_={},
    )
    db_session.add(rogue_site)

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_lubrication_point_cannot_span_tenants(db_session: AsyncSession) -> None:
    tenant_a = await make_tenant(db_session)
    tenant_b = await make_tenant(db_session)

    customer_a = await make_customer(db_session, tenant_a)
    site_a = await make_site(db_session, tenant_a, customer_a)
    plant_a = await make_plant(db_session, tenant_a, site_a)
    line_a = await make_production_line(db_session, tenant_a, plant_a)
    machine_a = await make_machine(db_session, tenant_a, line_a)
    system_a = await make_lubrication_system(db_session, tenant_a, machine_a)
    circuit_a = await make_circuit(db_session, tenant_a, system_a)

    customer_b = await make_customer(db_session, tenant_b)
    site_b = await make_site(db_session, tenant_b, customer_b)
    plant_b = await make_plant(db_session, tenant_b, site_b)
    line_b = await make_production_line(db_session, tenant_b, plant_b)
    machine_b = await make_machine(db_session, tenant_b, line_b)
    bearing_b = await make_bearing(db_session, tenant_b, machine_b)

    # Point claims tenant_a (matching its circuit) but its bearing belongs to tenant_b.
    rogue_point = LubricationPoint(
        tenant_id=tenant_a.id,
        circuit_id=circuit_a.id,
        bearing_id=bearing_b.id,
        name="Rogue Point",
        code=unique("LP"),
        status=OperationalStatus.ACTIVE,
        metadata_={},
    )
    db_session.add(rogue_point)

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_sensor_requires_exactly_one_attachment_not_zero(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    sensor = Sensor(
        tenant_id=tenant.id,
        sensor_code=unique("SENSOR"),
        name="Orphan sensor",
        sensor_type="VIBRATION_RMS",
        status="ACTIVE",
        quality_state="UNKNOWN",
        metadata_={},
    )
    db_session.add(sensor)

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_sensor_requires_exactly_one_attachment_not_two(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    customer = await make_customer(db_session, tenant)
    site = await make_site(db_session, tenant, customer)
    plant = await make_plant(db_session, tenant, site)
    line = await make_production_line(db_session, tenant, plant)
    machine = await make_machine(db_session, tenant, line)
    bearing = await make_bearing(db_session, tenant, machine)

    sensor = Sensor(
        tenant_id=tenant.id,
        sensor_code=unique("SENSOR"),
        name="Double-attached sensor",
        sensor_type="VIBRATION_RMS",
        status="ACTIVE",
        quality_state="UNKNOWN",
        machine_id=machine.id,
        bearing_id=bearing.id,
        metadata_={},
    )
    db_session.add(sensor)

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_gateway_requires_exactly_one_attachment(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    gateway = Gateway(
        tenant_id=tenant.id,
        gateway_code=unique("GW"),
        name="Orphan gateway",
        status="ACTIVE",
        metadata_={},
    )
    db_session.add(gateway)

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_duplicate_asset_code_within_tenant_is_rejected(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    customer = await make_customer(db_session, tenant)
    site = await make_site(db_session, tenant, customer)
    plant = await make_plant(db_session, tenant, site)
    line = await make_production_line(db_session, tenant, plant)

    shared_code = unique("ASSET")
    db_session.add(
        Machine(
            tenant_id=tenant.id,
            production_line_id=line.id,
            name="First",
            asset_code=shared_code,
            machine_type="MOTOR",
            criticality="MEDIUM",
            status="MONITORED",
            operating_profile={},
            metadata_={},
        )
    )
    await db_session.flush()

    db_session.add(
        Machine(
            tenant_id=tenant.id,
            production_line_id=line.id,
            name="Second",
            asset_code=shared_code,
            machine_type="MOTOR",
            criticality="MEDIUM",
            status="MONITORED",
            operating_profile={},
            metadata_={},
        )
    )

    with pytest.raises(IntegrityError):
        await db_session.flush()
