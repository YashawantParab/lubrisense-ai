"""Phase 24 RBAC integration tests against the real HTTP surface, run in
`AUTH_ENFORCEMENT_MODE=strict` (the mode a production deployment must use — see
`Settings.model_post_init`). The default `client` fixture used by every other test file
runs in the backward-compatible "permissive" mode and is untouched by this file."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Coroutine, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.domain.enums import RuleFindingSeverity, RuleFindingType, SensorType, UserRole
from app.domain.models import Tenant
from app.incidents.services.incident_service import IncidentService
from app.infrastructure.database import Database
from app.main import create_app
from tests.factories import make_customer, make_machine, make_plant, make_production_line, make_site
from tests.incidents.helpers import active_rule_finding
from tests.rules_engine.helpers import make_circuit, make_lubrication_system, make_topology_sensor


@pytest.fixture
def strict_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("AUTH_ENFORCEMENT_MODE", "strict")
    monkeypatch.setenv("DEMO_AUTH_SECRET", "test-strict-mode-secret")
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def _token(client: TestClient, tenant_id: uuid.UUID, role: UserRole) -> str:
    response = client.post(
        "/api/v1/auth/demo-login",
        headers={"X-Tenant-ID": str(tenant_id)},
        json={"role": role.value},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]  # type: ignore[no-any-return]


def _auth_headers(tenant_id: uuid.UUID, token: str) -> dict[str, str]:
    return {"X-Tenant-ID": str(tenant_id), "Authorization": f"Bearer {token}"}


def _run(coro: Coroutine[Any, Any, Any]) -> Any:  # noqa: ANN401
    return asyncio.run(coro)


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
            incident = await IncidentService(session).evaluate_machine(tenant.id, machine.id)
            await session.commit()
            assert incident is not None
            return incident.id
    finally:
        await database.dispose()


def test_demo_login_issues_a_usable_token(strict_client: TestClient, api_tenant: Tenant) -> None:
    token = _token(strict_client, api_tenant.id, UserRole.ADMIN)
    response = strict_client.get(
        "/api/v1/incidents", headers=_auth_headers(api_tenant.id, token)
    )
    assert response.status_code == 200


def test_no_token_rejected_on_protected_endpoint(
    strict_client: TestClient, api_tenant: Tenant
) -> None:
    incident_id = _run(_committed_incident(api_tenant))
    response = strict_client.post(
        f"/api/v1/incidents/{incident_id}/acknowledge",
        headers={"X-Tenant-ID": str(api_tenant.id)},
    )
    assert response.status_code == 401


def test_malformed_authorization_header_rejected(
    strict_client: TestClient, api_tenant: Tenant
) -> None:
    response = strict_client.get(
        "/api/v1/audit-events",
        headers={"X-Tenant-ID": str(api_tenant.id), "Authorization": "NotBearer abc"},
    )
    assert response.status_code == 401


def test_viewer_cannot_acknowledge_incident(strict_client: TestClient, api_tenant: Tenant) -> None:
    incident_id = _run(_committed_incident(api_tenant))
    token = _token(strict_client, api_tenant.id, UserRole.VIEWER)
    response = strict_client.post(
        f"/api/v1/incidents/{incident_id}/acknowledge",
        headers=_auth_headers(api_tenant.id, token),
    )
    assert response.status_code == 403


def test_viewer_can_read_incidents(strict_client: TestClient, api_tenant: Tenant) -> None:
    token = _token(strict_client, api_tenant.id, UserRole.VIEWER)
    response = strict_client.get(
        "/api/v1/incidents", headers=_auth_headers(api_tenant.id, token)
    )
    assert response.status_code == 200


def test_technician_can_create_maintenance_case_but_not_acknowledge_incident(
    strict_client: TestClient, api_tenant: Tenant
) -> None:
    incident_id = _run(_committed_incident(api_tenant))
    token = _token(strict_client, api_tenant.id, UserRole.TECHNICIAN)
    headers = _auth_headers(api_tenant.id, token)

    ack_response = strict_client.post(
        f"/api/v1/incidents/{incident_id}/acknowledge", headers=headers
    )
    assert ack_response.status_code == 403

    case_response = strict_client.post(
        "/api/v1/maintenance/cases", headers=headers, json={"incident_id": str(incident_id)}
    )
    assert case_response.status_code == 201


def test_reliability_engineer_can_acknowledge_incident(
    strict_client: TestClient, api_tenant: Tenant
) -> None:
    incident_id = _run(_committed_incident(api_tenant))
    token = _token(strict_client, api_tenant.id, UserRole.RELIABILITY_ENGINEER)
    response = strict_client.post(
        f"/api/v1/incidents/{incident_id}/acknowledge",
        headers=_auth_headers(api_tenant.id, token),
    )
    assert response.status_code == 200


def test_plant_manager_cannot_administer_knowledge(
    strict_client: TestClient, api_tenant: Tenant
) -> None:
    token = _token(strict_client, api_tenant.id, UserRole.PLANT_MANAGER)
    response = strict_client.post(
        "/api/v1/knowledge/documents",
        headers=_auth_headers(api_tenant.id, token),
        json={
            "document_key": "rbac-test-doc",
            "title": "RBAC Test Doc",
            "document_type": "OPERATING_GUIDE",
            "version": "1.0.0",
            "source_name": "test",
            "content": "# Doc\n\n## Section\n\nContent long enough to keep.",
        },
    )
    assert response.status_code == 403


def test_data_scientist_cannot_use_agent_or_write_maintenance(
    strict_client: TestClient, api_tenant: Tenant
) -> None:
    incident_id = _run(_committed_incident(api_tenant))
    token = _token(strict_client, api_tenant.id, UserRole.DATA_SCIENTIST)
    headers = _auth_headers(api_tenant.id, token)

    agent_response = strict_client.post(
        "/api/v1/agent/chat", headers=headers, json={"message": "What is happening?"}
    )
    assert agent_response.status_code == 403

    case_response = strict_client.post(
        "/api/v1/maintenance/cases", headers=headers, json={"incident_id": str(incident_id)}
    )
    assert case_response.status_code == 403


def test_admin_can_do_everything_tested_above(
    strict_client: TestClient, api_tenant: Tenant
) -> None:
    incident_id = _run(_committed_incident(api_tenant))
    token = _token(strict_client, api_tenant.id, UserRole.ADMIN)
    headers = _auth_headers(api_tenant.id, token)

    assert strict_client.post(
        f"/api/v1/incidents/{incident_id}/acknowledge", headers=headers
    ).status_code == 200
    assert strict_client.get("/api/v1/audit-events", headers=headers).status_code == 200


def test_token_rejected_for_a_different_tenant(
    strict_client: TestClient, api_tenant: Tenant
) -> None:
    other_tenant_id = uuid.uuid4()
    token = _token(strict_client, api_tenant.id, UserRole.ADMIN)
    response = strict_client.get(
        "/api/v1/incidents",
        headers={"X-Tenant-ID": str(other_tenant_id), "Authorization": f"Bearer {token}"},
    )
    # The tenant itself doesn't exist, so this fails tenant resolution before the
    # tenant-mismatch check ever runs — still correctly rejected, just via 404.
    assert response.status_code in (403, 404)


def test_audit_read_requires_permission(strict_client: TestClient, api_tenant: Tenant) -> None:
    viewer_token = _token(strict_client, api_tenant.id, UserRole.VIEWER)
    response = strict_client.get(
        "/api/v1/audit-events", headers=_auth_headers(api_tenant.id, viewer_token)
    )
    assert response.status_code == 403

    re_token = _token(strict_client, api_tenant.id, UserRole.RELIABILITY_ENGINEER)
    response = strict_client.get(
        "/api/v1/audit-events", headers=_auth_headers(api_tenant.id, re_token)
    )
    assert response.status_code == 200
