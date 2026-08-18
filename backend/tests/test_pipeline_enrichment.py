"""`ContextEnrichmentService` tests — hierarchy resolution and tenant/entity/context
validation against the real Phase 2 domain tables (live Postgres, via `db_session`)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import QuarantineReason
from app.pipeline.enrichment import ContextEnrichmentService, EnrichedContext, EnrichmentFailure
from app.pipeline.validation import ValidatedTelemetry
from tests.factories import (
    make_bearing,
    make_circuit,
    make_customer,
    make_gateway,
    make_lubrication_system,
    make_machine,
    make_plant,
    make_production_line,
    make_sensor,
    make_site,
    make_tenant,
)


def _event(**overrides: object) -> ValidatedTelemetry:
    now = datetime.now(UTC)
    base: dict[str, object] = {
        "event_id": uuid.uuid4(),
        "schema_version": "1",
        "correlation_id": str(uuid.uuid4()),
        "tenant_id": uuid.uuid4(),
        "site_id": None,
        "plant_id": None,
        "line_id": None,
        "machine_id": uuid.uuid4(),
        "bearing_id": None,
        "lubrication_system_id": None,
        "circuit_id": None,
        "lubrication_point_id": None,
        "component_id": None,
        "sensor_id": uuid.uuid4(),
        "measurement_type": "PRESSURE",
        "value": 1.0,
        "unit": "bar",
        "quality": "GOOD",
        "operating_state": "RUNNING_NORMAL_LOAD",
        "source_timestamp": now,
        "edge_received_timestamp": now,
        "edge_emitted_timestamp": None,
        "sequence_number": 1,
        "gateway_id": "GW-TEST",
        "device_id": "sim-device",
        "firmware_version": None,
        "controller_version": None,
        "source": "synthetic",
        "metadata": {},
    }
    base.update(overrides)
    return ValidatedTelemetry(**base)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_machine_attached_sensor_resolves_full_chain(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    site = await make_site(db_session, tenant, await make_customer(db_session, tenant))
    plant = await make_plant(db_session, tenant, site)
    line = await make_production_line(db_session, tenant, plant)
    machine = await make_machine(db_session, tenant, line)
    sensor = await make_sensor(db_session, tenant, machine_id=machine.id)
    gateway = await make_gateway(db_session, tenant, plant_id=plant.id)

    event = _event(
        tenant_id=tenant.id,
        sensor_id=sensor.id,
        machine_id=machine.id,
        gateway_id=gateway.gateway_code,
    )

    result = await ContextEnrichmentService(db_session).enrich(event)

    assert isinstance(result, EnrichedContext)
    assert result.machine_id == machine.id
    assert result.production_line_id == line.id
    assert result.plant_id == plant.id
    assert result.site_id == site.id
    assert result.bearing_id is None
    assert result.lubrication_system_id is None


@pytest.mark.asyncio
async def test_bearing_attached_sensor_resolves_via_bearing(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    site = await make_site(db_session, tenant, await make_customer(db_session, tenant))
    plant = await make_plant(db_session, tenant, site)
    line = await make_production_line(db_session, tenant, plant)
    machine = await make_machine(db_session, tenant, line)
    bearing = await make_bearing(db_session, tenant, machine)
    sensor = await make_sensor(db_session, tenant, bearing_id=bearing.id)
    gateway = await make_gateway(db_session, tenant, plant_id=plant.id)

    event = _event(
        tenant_id=tenant.id,
        sensor_id=sensor.id,
        machine_id=machine.id,
        gateway_id=gateway.gateway_code,
    )
    result = await ContextEnrichmentService(db_session).enrich(event)

    assert isinstance(result, EnrichedContext)
    assert result.machine_id == machine.id
    assert result.bearing_id == bearing.id
    assert result.lubrication_system_id is None


@pytest.mark.asyncio
async def test_circuit_attached_sensor_resolves_via_lubrication_system(
    db_session: AsyncSession,
) -> None:
    tenant = await make_tenant(db_session)
    site = await make_site(db_session, tenant, await make_customer(db_session, tenant))
    plant = await make_plant(db_session, tenant, site)
    line = await make_production_line(db_session, tenant, plant)
    machine = await make_machine(db_session, tenant, line)
    system = await make_lubrication_system(db_session, tenant, machine)
    circuit = await make_circuit(db_session, tenant, system)
    sensor = await make_sensor(db_session, tenant, circuit_id=circuit.id)
    gateway = await make_gateway(db_session, tenant, plant_id=plant.id)

    event = _event(
        tenant_id=tenant.id,
        sensor_id=sensor.id,
        machine_id=machine.id,
        gateway_id=gateway.gateway_code,
    )
    result = await ContextEnrichmentService(db_session).enrich(event)

    assert isinstance(result, EnrichedContext)
    assert result.machine_id == machine.id
    assert result.circuit_id == circuit.id
    assert result.lubrication_system_id == system.id


@pytest.mark.asyncio
async def test_unknown_tenant_is_rejected(db_session: AsyncSession) -> None:
    event = _event(tenant_id=uuid.uuid4())
    result = await ContextEnrichmentService(db_session).enrich(event)
    assert isinstance(result, EnrichmentFailure)
    assert result.reason == QuarantineReason.UNKNOWN_TENANT


@pytest.mark.asyncio
async def test_unknown_sensor_is_rejected(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    event = _event(tenant_id=tenant.id, sensor_id=uuid.uuid4())
    result = await ContextEnrichmentService(db_session).enrich(event)
    assert isinstance(result, EnrichmentFailure)
    assert result.reason == QuarantineReason.UNKNOWN_SENSOR


@pytest.mark.asyncio
async def test_unknown_gateway_is_rejected(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    site = await make_site(db_session, tenant, await make_customer(db_session, tenant))
    plant = await make_plant(db_session, tenant, site)
    line = await make_production_line(db_session, tenant, plant)
    machine = await make_machine(db_session, tenant, line)
    sensor = await make_sensor(db_session, tenant, machine_id=machine.id)

    event = _event(
        tenant_id=tenant.id,
        sensor_id=sensor.id,
        machine_id=machine.id,
        gateway_id="GW-DOES-NOT-EXIST",
    )
    result = await ContextEnrichmentService(db_session).enrich(event)
    assert isinstance(result, EnrichmentFailure)
    assert result.reason == QuarantineReason.UNKNOWN_GATEWAY


@pytest.mark.asyncio
async def test_gateway_id_resolves_by_uuid_not_only_by_code(db_session: AsyncSession) -> None:
    """The real edge (`edge.acquisition.builder.EnvelopeBuilder`) sends `Gateway.id` (a
    UUID) as the wire `gateway_id`, not `gateway_code` — a real mismatch caught during
    Phase 6 multi-asset acceptance testing. Resolution must succeed against the UUID."""
    tenant = await make_tenant(db_session)
    site = await make_site(db_session, tenant, await make_customer(db_session, tenant))
    plant = await make_plant(db_session, tenant, site)
    line = await make_production_line(db_session, tenant, plant)
    machine = await make_machine(db_session, tenant, line)
    sensor = await make_sensor(db_session, tenant, machine_id=machine.id)
    gateway = await make_gateway(db_session, tenant, plant_id=plant.id)

    event = _event(
        tenant_id=tenant.id,
        sensor_id=sensor.id,
        machine_id=machine.id,
        gateway_id=str(gateway.id),  # UUID, not gateway.gateway_code
    )
    result = await ContextEnrichmentService(db_session).enrich(event)
    assert isinstance(result, EnrichedContext)


@pytest.mark.asyncio
async def test_cross_tenant_sensor_is_rejected_as_unknown(db_session: AsyncSession) -> None:
    """A sensor_id that is real, but belongs to a *different* tenant, must not resolve —
    proves tenant isolation at the pipeline layer, not just the composite-FK schema."""
    tenant_a = await make_tenant(db_session)
    tenant_b = await make_tenant(db_session)
    site = await make_site(db_session, tenant_a, await make_customer(db_session, tenant_a))
    plant = await make_plant(db_session, tenant_a, site)
    line = await make_production_line(db_session, tenant_a, plant)
    machine = await make_machine(db_session, tenant_a, line)
    sensor = await make_sensor(db_session, tenant_a, machine_id=machine.id)

    event = _event(tenant_id=tenant_b.id, sensor_id=sensor.id, machine_id=machine.id)
    result = await ContextEnrichmentService(db_session).enrich(event)
    assert isinstance(result, EnrichmentFailure)
    assert result.reason == QuarantineReason.UNKNOWN_SENSOR


@pytest.mark.asyncio
async def test_conflicting_supplied_machine_id_is_quarantined(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    site = await make_site(db_session, tenant, await make_customer(db_session, tenant))
    plant = await make_plant(db_session, tenant, site)
    line = await make_production_line(db_session, tenant, plant)
    machine = await make_machine(db_session, tenant, line)
    other_machine = await make_machine(db_session, tenant, line)
    sensor = await make_sensor(db_session, tenant, machine_id=machine.id)
    gateway = await make_gateway(db_session, tenant, plant_id=plant.id)

    event = _event(
        tenant_id=tenant.id,
        sensor_id=sensor.id,
        machine_id=other_machine.id,  # deliberately wrong
        gateway_id=gateway.gateway_code,
    )
    result = await ContextEnrichmentService(db_session).enrich(event)
    assert isinstance(result, EnrichmentFailure)
    assert result.reason == QuarantineReason.CONTEXT_CONFLICT


@pytest.mark.asyncio
async def test_conflicting_supplied_site_id_is_quarantined_not_overwritten(
    db_session: AsyncSession,
) -> None:
    tenant = await make_tenant(db_session)
    site = await make_site(db_session, tenant, await make_customer(db_session, tenant))
    plant = await make_plant(db_session, tenant, site)
    line = await make_production_line(db_session, tenant, plant)
    machine = await make_machine(db_session, tenant, line)
    sensor = await make_sensor(db_session, tenant, machine_id=machine.id)
    gateway = await make_gateway(db_session, tenant, plant_id=plant.id)

    event = _event(
        tenant_id=tenant.id,
        sensor_id=sensor.id,
        machine_id=machine.id,
        site_id=uuid.uuid4(),  # deliberately wrong, doesn't match the resolved site
        gateway_id=gateway.gateway_code,
    )
    result = await ContextEnrichmentService(db_session).enrich(event)
    assert isinstance(result, EnrichmentFailure)
    assert result.reason == QuarantineReason.CONTEXT_CONFLICT
