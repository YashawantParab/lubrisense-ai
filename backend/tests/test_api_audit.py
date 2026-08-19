"""Phase 25 audit integration tests against the real HTTP surface: human action ->
HUMAN audit, system incident creation -> SYSTEM audit, agent draft -> AGENT audit,
correlation IDs present, no secret leakage, tenant-scoped read API."""

from __future__ import annotations

import asyncio
import uuid

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.domain.enums import RuleFindingSeverity, RuleFindingType, SensorType
from app.domain.models import Tenant
from app.incidents.services.incident_service import IncidentService
from app.infrastructure.database import Database
from tests.factories import make_customer, make_machine, make_plant, make_production_line, make_site
from tests.incidents.helpers import active_rule_finding
from tests.rules_engine.helpers import make_circuit, make_lubrication_system, make_topology_sensor


async def _committed_incident(tenant: Tenant) -> tuple[uuid.UUID, uuid.UUID]:
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
            await session.commit()
            assert incident is not None
            return machine.id, incident.id
    finally:
        await database.dispose()


def test_incident_creation_produces_system_audit_event(
    client: TestClient, api_tenant: Tenant
) -> None:
    _machine_id, incident_id = asyncio.run(_committed_incident(api_tenant))
    headers = {"X-Tenant-ID": str(api_tenant.id)}

    response = client.get(
        "/api/v1/audit-events",
        headers=headers,
        params={
            "entity_type": "incident",
            "entity_id": str(incident_id),
            "action": "INCIDENT_CREATED",
        },
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    event = items[0]
    assert event["actor_type"] == "SYSTEM"
    assert event["correlation_id"]


def test_incident_acknowledge_produces_human_audit_event(
    client: TestClient, api_tenant: Tenant
) -> None:
    _machine_id, incident_id = asyncio.run(_committed_incident(api_tenant))
    headers = {"X-Tenant-ID": str(api_tenant.id)}

    ack = client.post(f"/api/v1/incidents/{incident_id}/acknowledge", headers=headers)
    assert ack.status_code == 200

    response = client.get(
        "/api/v1/audit-events",
        headers=headers,
        params={"action": "INCIDENT_ACKNOWLEDGED", "entity_id": str(incident_id)},
    )
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["actor_type"] == "HUMAN"
    assert items[0]["role"] == "ADMIN"  # permissive-mode fallback principal


def test_agent_draft_produces_agent_audit_event(client: TestClient, api_tenant: Tenant) -> None:
    machine_id, incident_id = asyncio.run(_committed_incident(api_tenant))
    headers = {"X-Tenant-ID": str(api_tenant.id)}

    case_response = client.post(
        "/api/v1/maintenance/cases", headers=headers, json={"incident_id": str(incident_id)}
    )
    assert case_response.status_code == 201
    case_id = case_response.json()["id"]

    chat_response = client.post(
        "/api/v1/agent/chat",
        headers=headers,
        json={
            "message": "Please prepare a checklist for this issue.",
            "machine_id": str(machine_id),
            "incident_id": str(incident_id),
            "maintenance_case_id": case_id,
        },
    )
    assert chat_response.status_code == 200
    session_id = chat_response.json()["session_id"]

    response = client.get(
        "/api/v1/audit-events",
        headers=headers,
        params={"action": "AGENT_DRAFT_GENERATED", "entity_id": session_id},
    )
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["actor_type"] == "AGENT"


def test_audit_events_are_tenant_scoped(client: TestClient, api_tenant: Tenant) -> None:
    asyncio.run(_committed_incident(api_tenant))
    other_tenant_headers = {"X-Tenant-ID": str(uuid.uuid4())}
    response = client.get("/api/v1/audit-events", headers=other_tenant_headers)
    assert response.status_code == 404  # unknown tenant, fails closed


def test_audit_event_never_contains_a_secret_looking_value(
    client: TestClient, api_tenant: Tenant
) -> None:
    asyncio.run(_committed_incident(api_tenant))
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    response = client.get("/api/v1/audit-events", headers=headers)
    payload = response.text.lower()
    for forbidden in ("password", "secret", "bearer ", "api_key", "apikey"):
        assert forbidden not in payload
