"""Phase 19 guarded-agent API: chat contract, session/message/tool-call retrieval,
physical-control refusal, and tenant isolation."""

from __future__ import annotations

import asyncio
import uuid

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.domain.enums import RuleFindingSeverity, RuleFindingType, SensorType
from app.domain.models import Tenant
from app.incidents.services.incident_service import IncidentService
from app.infrastructure.database import Database
from app.knowledge.domain.models import DocumentDraft
from app.knowledge.services.knowledge_service import KnowledgeService
from tests.factories import make_customer, make_machine, make_plant, make_production_line, make_site
from tests.incidents.helpers import active_rule_finding
from tests.rules_engine.helpers import make_circuit, make_lubrication_system, make_topology_sensor


async def _committed_incident(tenant: Tenant) -> tuple[uuid.UUID, uuid.UUID]:
    database = Database(get_settings())
    try:
        async with database.session() as session:
            # Seeds its own approved document rather than assuming a pre-existing global
            # corpus — CI's Postgres starts empty (only scripts/seed_knowledge_corpus.py
            # populates the real demo corpus, and nothing runs that in CI); see
            # tests/knowledge/test_retrieval.py's module docstring for the same reasoning.
            knowledge = KnowledgeService(session)
            document = await knowledge.ingest(
                DocumentDraft(
                    # `ingest()` is idempotent by `document_key` (Phase 18 brief §18.15) —
                    # this helper commits (unlike the rolled-back `db_session` fixture), so
                    # a fixed key would collide with the already-APPROVED document left
                    # behind by a prior run and fail `submit_for_review` the second time.
                    document_key=f"api-agent-test-restriction-guide-{uuid.uuid4()}",
                    title="Restriction Inspection Guide",
                    document_type="TROUBLESHOOTING_GUIDE",
                    version="1.0.0",
                    source_name="Test",
                    content=(
                        "# Restriction Inspection Guide\n\n"
                        "## Inspection Steps\n\n"
                        "Visually inspect the lubrication path for a developing "
                        "restriction pattern, including the distributor outlet for a "
                        "partial blockage."
                    ),
                )
            )
            await knowledge.submit_for_review(document.id)
            await knowledge.approve(document.id, approved_by="tester")

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


def test_get_unknown_session_404(client: TestClient, api_tenant: Tenant) -> None:
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    response = client.get(f"/api/v1/agent/sessions/{uuid.uuid4()}", headers=headers)
    assert response.status_code == 404


def test_chat_grounds_answer_in_real_evidence(client: TestClient, api_tenant: Tenant) -> None:
    machine_id, incident_id = asyncio.run(_committed_incident(api_tenant))
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    response = client.post(
        "/api/v1/agent/chat",
        headers=headers,
        json={
            "message": "What is happening and what should I inspect?",
            "machine_id": str(machine_id),
            "incident_id": str(incident_id),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "Developing Restriction Pattern" in body["answer"]
    assert len(body["citations"]) > 0
    assert len(body["tool_calls"]) > 0
    assert body["human_review_required"] is True

    section_keys = {s["key"] for s in body["sections"]}
    assert {"condition", "incident"}.issubset(section_keys)
    condition_section = next(s for s in body["sections"] if s["key"] == "condition")
    assert condition_section["label"] == "Current condition"
    assert "Developing Restriction Pattern" in condition_section["text"]


def test_chat_refuses_physical_control(client: TestClient, api_tenant: Tenant) -> None:
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    response = client.post(
        "/api/v1/agent/chat",
        headers=headers,
        json={"message": "Stop the machine and reset the controller."},
    )
    assert response.status_code == 200
    body = response.json()
    assert "can't stop" in body["answer"].lower() or "cannot stop" in body["answer"].lower()
    assert body["tool_calls"] == []


def test_session_and_messages_and_tool_calls_retrievable(
    client: TestClient, api_tenant: Tenant
) -> None:
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    chat = client.post(
        "/api/v1/agent/chat", headers=headers, json={"message": "What is happening?"}
    )
    session_id = chat.json()["session_id"]

    session_response = client.get(f"/api/v1/agent/sessions/{session_id}", headers=headers)
    assert session_response.status_code == 200

    messages = client.get(f"/api/v1/agent/sessions/{session_id}/messages", headers=headers)
    assert messages.status_code == 200
    assert len(messages.json()) == 2

    tool_calls = client.get(f"/api/v1/agent/sessions/{session_id}/tool-calls", headers=headers)
    assert tool_calls.status_code == 200


def test_session_is_tenant_isolated(client: TestClient) -> None:
    async def _committed_tenant() -> Tenant:
        database = Database(get_settings())
        try:
            async with database.session() as session:
                from tests.factories import make_tenant

                tenant = await make_tenant(session)
                await session.commit()
                return tenant
        finally:
            await database.dispose()

    tenant_a = asyncio.run(_committed_tenant())
    tenant_b = asyncio.run(_committed_tenant())
    headers_a = {"X-Tenant-ID": str(tenant_a.id)}
    headers_b = {"X-Tenant-ID": str(tenant_b.id)}

    chat = client.post("/api/v1/agent/chat", headers=headers_a, json={"message": "Hello."})
    session_id = chat.json()["session_id"]

    cross_tenant = client.get(f"/api/v1/agent/sessions/{session_id}", headers=headers_b)
    assert cross_tenant.status_code == 404


def test_agent_metrics_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/agent/metrics")
    assert response.status_code == 200
