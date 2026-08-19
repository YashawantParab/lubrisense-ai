"""`CustomerOverviewService` — real-Postgres integration tests (Phase 21 brief §21.2-
§21.4): asset coverage, operational status precedence, and the "no machine == UNKNOWN,
never HEALTHY" invariant."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.customer_services.service import CustomerOverviewService
from app.domain.enums import CustomerOperationalStatus, SensorType, TelemetryQuality
from app.domain.models import Machine, Sensor, Telemetry, Tenant
from tests.factories import (
    make_customer,
    make_machine,
    make_plant,
    make_production_line,
    make_sensor,
    make_site,
    make_tenant,
)


async def _make_recent_telemetry(
    session: AsyncSession, tenant: Tenant, machine: Machine, sensor: Sensor
) -> None:
    now = datetime.now(UTC)
    session.add(
        Telemetry(
            event_id=uuid.uuid4(),
            schema_version="1",
            correlation_id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            machine_id=machine.id,
            sensor_id=sensor.id,
            measurement_type=sensor.sensor_type,
            value=1.0,
            unit="bar",
            quality=TelemetryQuality.GOOD,
            operating_state="RUNNING",
            source_timestamp=now,
            edge_received_timestamp=now,
            mqtt_received_timestamp=now,
            consumer_received_timestamp=now,
            sequence_number=1,
            gateway_id="test-gateway",
            device_id="test-device",
            source="synthetic",
        )
    )
    await session.flush()


@pytest.mark.asyncio
async def test_customer_with_no_machines_is_unknown_not_healthy(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    customer = await make_customer(db_session, tenant)

    overview = await CustomerOverviewService(db_session).customer_overview(tenant.id, customer.id)

    assert overview.status == CustomerOperationalStatus.UNKNOWN
    assert overview.total_machines == 0
    assert overview.asset_coverage.instrumentation_coverage_ratio is None


@pytest.mark.asyncio
async def test_uninstrumented_machine_is_degraded_visibility_not_healthy(
    db_session: AsyncSession,
) -> None:
    tenant = await make_tenant(db_session)
    customer = await make_customer(db_session, tenant)
    site = await make_site(db_session, tenant, customer)
    plant = await make_plant(db_session, tenant, site)
    line = await make_production_line(db_session, tenant, plant)
    await make_machine(db_session, tenant, line)  # no sensor attached

    overview = await CustomerOverviewService(db_session).customer_overview(tenant.id, customer.id)

    assert overview.status == CustomerOperationalStatus.DEGRADED_VISIBILITY
    assert overview.asset_coverage.instrumented_machines == 0
    assert overview.total_machines == 1


@pytest.mark.asyncio
async def test_instrumented_machine_with_no_telemetry_yet_is_degraded_visibility(
    db_session: AsyncSession,
) -> None:
    """A sensor exists but has never reported — genuinely degraded visibility, not a
    silently-assumed HEALTHY status (CLAUDE.md "do not treat uninstrumented assets as
    healthy" extended to "do not treat non-reporting assets as healthy" either)."""
    tenant = await make_tenant(db_session)
    customer = await make_customer(db_session, tenant)
    site = await make_site(db_session, tenant, customer)
    plant = await make_plant(db_session, tenant, site)
    line = await make_production_line(db_session, tenant, plant)
    machine = await make_machine(db_session, tenant, line)
    await make_sensor(db_session, tenant, SensorType.PRESSURE, machine_id=machine.id)

    overview = await CustomerOverviewService(db_session).customer_overview(tenant.id, customer.id)

    assert overview.status == CustomerOperationalStatus.DEGRADED_VISIBILITY
    assert overview.asset_coverage.instrumented_machines == 1
    assert overview.asset_coverage.machines_with_recent_telemetry == 0


@pytest.mark.asyncio
async def test_instrumented_and_reporting_machine_with_no_incidents_is_healthy(
    db_session: AsyncSession,
) -> None:
    tenant = await make_tenant(db_session)
    customer = await make_customer(db_session, tenant)
    site = await make_site(db_session, tenant, customer)
    plant = await make_plant(db_session, tenant, site)
    line = await make_production_line(db_session, tenant, plant)
    machine = await make_machine(db_session, tenant, line)
    sensor = await make_sensor(db_session, tenant, SensorType.PRESSURE, machine_id=machine.id)
    await _make_recent_telemetry(db_session, tenant, machine, sensor)

    overview = await CustomerOverviewService(db_session).customer_overview(tenant.id, customer.id)

    assert overview.status == CustomerOperationalStatus.HEALTHY
    assert overview.asset_coverage.instrumented_machines == 1
    assert overview.asset_coverage.machines_with_recent_telemetry == 1
    assert overview.operations.active_incidents == 0


@pytest.mark.asyncio
async def test_fleet_overview_aggregates_across_customers(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    customer_a = await make_customer(db_session, tenant)
    customer_b = await make_customer(db_session, tenant)
    for customer in (customer_a, customer_b):
        site = await make_site(db_session, tenant, customer)
        plant = await make_plant(db_session, tenant, site)
        line = await make_production_line(db_session, tenant, plant)
        machine = await make_machine(db_session, tenant, line)
        sensor = await make_sensor(db_session, tenant, SensorType.PRESSURE, machine_id=machine.id)
        await _make_recent_telemetry(db_session, tenant, machine, sensor)

    fleet = await CustomerOverviewService(db_session).fleet_overview(tenant.id)

    assert fleet.total_customer_accounts == 2
    assert fleet.total_machines == 2
    assert fleet.asset_coverage.instrumented_machines == 2
    assert fleet.customers_by_status.get("HEALTHY") == 2
