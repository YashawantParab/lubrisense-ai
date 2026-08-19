"""Phase 17 maintenance-workflow API: tenant scoping, contract shape, not-found handling,
and the create -> plan -> start -> finding -> action -> complete workflow plus the
Phase 20 cmms-draft sub-route, via the real HTTP surface."""

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


async def _committed_incident(tenant: Tenant) -> uuid.UUID:
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
            incidents = IncidentService(session)
            incident = await incidents.evaluate_machine(tenant.id, machine.id)
            assert incident is not None
            await incidents.acknowledge(tenant.id, incident.id)
            await incidents.start_investigation(tenant.id, incident.id)
            await session.commit()
            return incident.id
    finally:
        await database.dispose()


def test_create_case_incident_not_found(client: TestClient, api_tenant: Tenant) -> None:
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    response = client.post(
        "/api/v1/maintenance/cases", headers=headers, json={"incident_id": str(uuid.uuid4())}
    )
    assert response.status_code == 404


def test_list_cases_empty_for_fresh_tenant(client: TestClient, api_tenant: Tenant) -> None:
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    response = client.get("/api/v1/maintenance/cases", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


def test_get_case_not_found(client: TestClient, api_tenant: Tenant) -> None:
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    response = client.get(f"/api/v1/maintenance/cases/{uuid.uuid4()}", headers=headers)
    assert response.status_code == 404


def test_create_case_is_idempotent_via_api(client: TestClient, api_tenant: Tenant) -> None:
    incident_id = asyncio.run(_committed_incident(api_tenant))
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    first = client.post(
        "/api/v1/maintenance/cases", headers=headers, json={"incident_id": str(incident_id)}
    )
    second = client.post(
        "/api/v1/maintenance/cases", headers=headers, json={"incident_id": str(incident_id)}
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


def test_full_maintenance_workflow_via_api(client: TestClient, api_tenant: Tenant) -> None:
    incident_id = asyncio.run(_committed_incident(api_tenant))
    headers = {"X-Tenant-ID": str(api_tenant.id)}

    created = client.post(
        "/api/v1/maintenance/cases", headers=headers, json={"incident_id": str(incident_id)}
    )
    assert created.status_code == 201
    case_id = created.json()["id"]
    assert len(created.json()["checklist"]) > 0

    planned = client.post(f"/api/v1/maintenance/cases/{case_id}/plan", headers=headers, json={})
    assert planned.status_code == 200
    assert planned.json()["state"] == "PLANNED"

    started = client.post(f"/api/v1/maintenance/cases/{case_id}/start", headers=headers)
    assert started.status_code == 200
    assert started.json()["state"] == "IN_PROGRESS"

    finding = client.post(
        f"/api/v1/maintenance/cases/{case_id}/finding",
        headers=headers,
        json={
            "result": "PARTIALLY_CONFIRMED",
            "component": "distributor",
            "observed_issue": "Partially blocked distributor outlet (synthetic demo finding).",
            "notes": "Demo technician inspection.",
        },
    )
    assert finding.status_code == 200
    assert finding.json()["result"] == "PARTIALLY_CONFIRMED"

    action = client.post(
        f"/api/v1/maintenance/cases/{case_id}/action",
        headers=headers,
        json={"action_type": "CLEANED", "notes": "Cleaned distributor outlet."},
    )
    assert action.status_code == 200

    draft = client.post(f"/api/v1/maintenance/cases/{case_id}/cmms-draft", headers=headers)
    assert draft.status_code == 200
    assert draft.json()["status"] == "DRAFT"
    external_reference = draft.json()["external_reference"]

    work_order = client.get(f"/api/v1/cmms/work-orders/{external_reference}", headers=headers)
    assert work_order.status_code == 200
    assert work_order.json()["external_reference"] == external_reference

    completed = client.post(
        f"/api/v1/maintenance/cases/{case_id}/complete",
        headers=headers,
        json={"classification": "TRUE_POSITIVE", "notes": "Confirmed and cleared."},
    )
    assert completed.status_code == 200
    assert completed.json()["state"] == "COMPLETED"
    assert completed.json()["feedback_classification"] == "TRUE_POSITIVE"

    feedback = client.get(f"/api/v1/maintenance/cases/{case_id}/feedback", headers=headers)
    assert feedback.status_code == 200
    assert feedback.json()["classification"] == "TRUE_POSITIVE"

    incident_after = client.get(f"/api/v1/incidents/{incident_id}", headers=headers)
    assert incident_after.json()["state"] == "RESOLVED"


def test_starting_an_unplanned_case_returns_409(client: TestClient, api_tenant: Tenant) -> None:
    incident_id = asyncio.run(_committed_incident(api_tenant))
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    created = client.post(
        "/api/v1/maintenance/cases", headers=headers, json={"incident_id": str(incident_id)}
    )
    case_id = created.json()["id"]
    response = client.post(f"/api/v1/maintenance/cases/{case_id}/start", headers=headers)
    assert response.status_code == 409


def test_maintenance_metrics_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/maintenance/cases/metrics")
    assert response.status_code == 200
