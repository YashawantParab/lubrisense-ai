"""`CommissioningService` — real-Postgres integration tests (Phase 30 brief §30.2-
§30.6): the full guided workflow, capability-level computation, and the "flagship
missing-FLOW topology" case explicitly called out in §30.5."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import AuditActor
from app.commissioning.service import CommissioningService, InvalidCommissioningTransitionError
from app.domain.enums import (
    AuditActorType,
    CapabilityLevel,
    CommissioningStatus,
    MachineStatus,
    SensorType,
)
from app.repositories.machine import MachineRepository
from tests.factories import (
    make_customer,
    make_gateway,
    make_plant,
    make_production_line,
    make_site,
    make_tenant,
)


def _actor() -> AuditActor:
    return AuditActor(actor_id="test-admin", actor_type=AuditActorType.HUMAN, role="ADMIN")


@pytest.mark.asyncio
async def test_start_session_creates_commissioning_machine(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    customer = await make_customer(db_session, tenant)
    site = await make_site(db_session, tenant, customer)
    plant = await make_plant(db_session, tenant, site)
    line = await make_production_line(db_session, tenant, plant)

    service = CommissioningService(db_session)
    session = await service.start_session(
        tenant.id,
        production_line_id=line.id,
        name="New Demo Motor",
        asset_code="COMM-TEST-001",
        machine_type="MOTOR",
        actor=_actor(),
    )

    assert session.status == CommissioningStatus.CONFIGURING
    assert "machine_registered" in session.steps_completed

    machine = await MachineRepository(db_session).get(tenant.id, session.machine_id)
    assert machine is not None
    assert machine.status == MachineStatus.COMMISSIONING


@pytest.mark.asyncio
async def test_validate_with_no_sensors_is_blocking_failure(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    customer = await make_customer(db_session, tenant)
    site = await make_site(db_session, tenant, customer)
    plant = await make_plant(db_session, tenant, site)
    line = await make_production_line(db_session, tenant, plant)

    service = CommissioningService(db_session)
    session = await service.start_session(
        tenant.id,
        production_line_id=line.id,
        name="Uninstrumented Motor",
        asset_code="COMM-TEST-002",
        machine_type="MOTOR",
        actor=_actor(),
    )

    validated = await service.validate(tenant.id, session.id)

    assert validated.status == CommissioningStatus.FAILED
    assert validated.capability_level == CapabilityLevel.NONE
    codes = {issue["code"] for issue in validated.validation_issues}
    assert "NO_INSTRUMENTATION" in codes


@pytest.mark.asyncio
async def test_complete_requires_ready_state(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    customer = await make_customer(db_session, tenant)
    site = await make_site(db_session, tenant, customer)
    plant = await make_plant(db_session, tenant, site)
    line = await make_production_line(db_session, tenant, plant)

    service = CommissioningService(db_session)
    session = await service.start_session(
        tenant.id,
        production_line_id=line.id,
        name="Not Yet Ready Motor",
        asset_code="COMM-TEST-003",
        machine_type="MOTOR",
        actor=_actor(),
    )

    with pytest.raises(InvalidCommissioningTransitionError):
        await service.complete(tenant.id, session.id, actor=_actor())


@pytest.mark.asyncio
async def test_flagship_topology_without_flow_reaches_full_intelligence(
    db_session: AsyncSession,
) -> None:
    """The flagship reference topology has no FLOW sensor (Phase 30 brief §30.5) — this
    proves DELIVERY_INTELLIGENCE (and therefore FULL_INTELLIGENCE, once bearing evidence
    is also present) is reachable using PRESSURE + RESERVOIR_LEVEL alone."""
    tenant = await make_tenant(db_session)
    customer = await make_customer(db_session, tenant)
    site = await make_site(db_session, tenant, customer)
    plant = await make_plant(db_session, tenant, site)
    line = await make_production_line(db_session, tenant, plant)
    gateway = await make_gateway(db_session, tenant, site_id=site.id)

    service = CommissioningService(db_session)
    session = await service.start_session(
        tenant.id,
        production_line_id=line.id,
        name="Flagship Topology Motor",
        asset_code="COMM-TEST-004",
        machine_type="MOTOR",
        actor=_actor(),
    )

    await service.add_sensor(
        tenant.id,
        session.id,
        sensor_type=SensorType.PRESSURE,
        sensor_code="COMM-TEST-004-P1",
        name="Pressure 1",
        unit="bar",
        actor=_actor(),
    )
    await service.add_sensor(
        tenant.id,
        session.id,
        sensor_type=SensorType.RESERVOIR_LEVEL,
        sensor_code="COMM-TEST-004-R1",
        name="Reservoir 1",
        unit="%",
        actor=_actor(),
    )
    await service.add_sensor(
        tenant.id,
        session.id,
        sensor_type=SensorType.VIBRATION_RMS,
        sensor_code="COMM-TEST-004-V1",
        name="Vibration 1",
        unit="mm/s",
        actor=_actor(),
    )
    await service.assign_gateway(tenant.id, session.id, gateway_id=gateway.id, actor=_actor())

    validated = await service.validate(tenant.id, session.id)
    assert validated.status == CommissioningStatus.READY
    assert validated.capability_level == CapabilityLevel.FULL_INTELLIGENCE
    blocking_issues = [i for i in validated.validation_issues if i["blocking"]]
    assert blocking_issues == []

    completed = await service.complete(tenant.id, session.id, actor=_actor())
    assert completed.status == CommissioningStatus.COMPLETED
    assert completed.completed_at is not None

    machine = await MachineRepository(db_session).get(tenant.id, session.machine_id)
    assert machine is not None
    assert machine.status == MachineStatus.MONITORED


@pytest.mark.asyncio
async def test_delivery_only_capability_without_bearing_sensors(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    customer = await make_customer(db_session, tenant)
    site = await make_site(db_session, tenant, customer)
    plant = await make_plant(db_session, tenant, site)
    line = await make_production_line(db_session, tenant, plant)

    service = CommissioningService(db_session)
    session = await service.start_session(
        tenant.id,
        production_line_id=line.id,
        name="Delivery Only Motor",
        asset_code="COMM-TEST-005",
        machine_type="PUMP",
        actor=_actor(),
    )
    await service.add_sensor(
        tenant.id,
        session.id,
        sensor_type=SensorType.PRESSURE,
        sensor_code="COMM-TEST-005-P1",
        name="Pressure 1",
        unit="bar",
        actor=_actor(),
    )
    await service.add_sensor(
        tenant.id,
        session.id,
        sensor_type=SensorType.PUMP_CURRENT,
        sensor_code="COMM-TEST-005-C1",
        name="Pump current 1",
        unit="A",
        actor=_actor(),
    )

    validated = await service.validate(tenant.id, session.id)
    assert validated.capability_level == CapabilityLevel.DELIVERY_INTELLIGENCE
    # Not blocking, but a gateway was never assigned — surfaced as a non-blocking issue.
    codes = {issue["code"] for issue in validated.validation_issues}
    assert "NO_GATEWAY_ASSIGNED" in codes
    assert validated.status == CommissioningStatus.READY
