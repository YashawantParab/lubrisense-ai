"""Phase 16 incident-management API: tenant scoping, contract shape, machine/incident-
not-found handling, and the acknowledge -> start-investigation -> resolve -> close
lifecycle via the real HTTP surface."""

from __future__ import annotations

import asyncio
import uuid

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.domain.enums import RuleFindingSeverity, RuleFindingType, SensorType
from app.domain.models import Tenant
from app.incidents.services.incident_service import IncidentService
from app.infrastructure.database import Database
from tests.factories import (
    make_customer,
    make_machine,
    make_plant,
    make_production_line,
    make_site,
    make_tenant,
)
from tests.incidents.helpers import active_rule_finding
from tests.rules_engine.helpers import make_circuit, make_lubrication_system, make_topology_sensor


async def _committed_machine(tenant: Tenant) -> uuid.UUID:
    database = Database(get_settings())
    try:
        async with database.session() as session:
            customer = await make_customer(session, tenant)
            site = await make_site(session, tenant, customer)
            plant = await make_plant(session, tenant, site)
            line = await make_production_line(session, tenant, plant)
            machine = await make_machine(session, tenant, line)
            await session.commit()
            return machine.id
    finally:
        await database.dispose()


async def _committed_incident(tenant: Tenant) -> tuple[uuid.UUID, uuid.UUID]:
    """Returns `(machine_id, incident_id)` for a machine with a real, active restriction
    finding that has already been correlated into one open incident."""
    database = Database(get_settings())
    try:
        async with database.session() as session:
            customer = await make_customer(session, tenant)
            site = await make_site(session, tenant, customer)
            plant = await make_plant(session, tenant, site)
            line = await make_production_line(session, tenant, plant)
            machine = await make_machine(session, tenant, line)
            system = await make_lubrication_system(session, tenant, machine)
            circuit = await make_circuit(session, tenant, system)
            await make_topology_sensor(session, tenant, SensorType.PRESSURE, circuit_id=circuit.id)
            await active_rule_finding(
                session,
                tenant_id=tenant.id,
                machine_id=machine.id,
                finding_type=RuleFindingType.FLOW_PRESSURE_RESTRICTION_PATTERN,
                severity=RuleFindingSeverity.WARNING,
            )
            incident = await IncidentService(session).evaluate_machine(tenant.id, machine.id)
            assert incident is not None
            await session.commit()
            return machine.id, incident.id
    finally:
        await database.dispose()


async def _committed_tenant() -> Tenant:
    database = Database(get_settings())
    try:
        async with database.session() as session:
            tenant = await make_tenant(session)
            await session.commit()
            return tenant
    finally:
        await database.dispose()


def test_evaluate_machine_not_found(client: TestClient, api_tenant: Tenant) -> None:
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    response = client.post(f"/api/v1/incidents/machines/{uuid.uuid4()}/evaluate", headers=headers)
    assert response.status_code == 404


def test_evaluate_healthy_machine_returns_null(client: TestClient, api_tenant: Tenant) -> None:
    machine_id = asyncio.run(_committed_machine(api_tenant))
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    response = client.post(f"/api/v1/incidents/machines/{machine_id}/evaluate", headers=headers)
    assert response.status_code == 200
    assert response.json() is None


def test_get_incident_not_found(client: TestClient, api_tenant: Tenant) -> None:
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    response = client.get(f"/api/v1/incidents/{uuid.uuid4()}", headers=headers)
    assert response.status_code == 404


def test_cross_tenant_incident_not_found(client: TestClient) -> None:
    tenant_a = asyncio.run(_committed_tenant())
    tenant_b = asyncio.run(_committed_tenant())
    _machine_id, incident_id = asyncio.run(_committed_incident(tenant_a))
    headers_b = {"X-Tenant-ID": str(tenant_b.id)}
    response = client.get(f"/api/v1/incidents/{incident_id}", headers=headers_b)
    assert response.status_code == 404


def test_list_incidents_empty_for_fresh_tenant(client: TestClient) -> None:
    tenant = asyncio.run(_committed_tenant())
    headers = {"X-Tenant-ID": str(tenant.id)}
    response = client.get("/api/v1/incidents", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


def test_full_incident_lifecycle_via_api(client: TestClient) -> None:
    tenant = asyncio.run(_committed_tenant())
    _machine_id, incident_id = asyncio.run(_committed_incident(tenant))
    headers = {"X-Tenant-ID": str(tenant.id)}

    listed = client.get("/api/v1/incidents", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["id"] == str(incident_id)

    ack = client.post(f"/api/v1/incidents/{incident_id}/acknowledge", headers=headers)
    assert ack.status_code == 200
    assert ack.json()["state"] == "ACKNOWLEDGED"
    assert ack.json()["acknowledged_at"] is not None

    investigate = client.post(
        f"/api/v1/incidents/{incident_id}/start-investigation", headers=headers
    )
    assert investigate.status_code == 200
    assert investigate.json()["state"] == "INVESTIGATING"

    resolve = client.post(
        f"/api/v1/incidents/{incident_id}/resolve",
        headers=headers,
        json={"reason": "Confirmed fixed."},
    )
    assert resolve.status_code == 200
    assert resolve.json()["state"] == "RESOLVED"

    close = client.post(f"/api/v1/incidents/{incident_id}/close", headers=headers)
    assert close.status_code == 200
    assert close.json()["state"] == "CLOSED"

    timeline = client.get(f"/api/v1/incidents/{incident_id}/timeline", headers=headers)
    assert timeline.status_code == 200
    event_types = [e["event_type"] for e in timeline.json()]
    assert "INCIDENT_CREATED" in event_types
    assert "ACKNOWLEDGED" in event_types
    assert "INVESTIGATION_STARTED" in event_types
    assert "RESOLVED" in event_types
    assert "CLOSED" in event_types


def test_invalid_transition_returns_409(client: TestClient) -> None:
    tenant = asyncio.run(_committed_tenant())
    _machine_id, incident_id = asyncio.run(_committed_incident(tenant))
    headers = {"X-Tenant-ID": str(tenant.id)}
    response = client.post(f"/api/v1/incidents/{incident_id}/close", headers=headers)
    assert response.status_code == 409


def test_incident_metrics_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/incidents/metrics")
    assert response.status_code == 200
