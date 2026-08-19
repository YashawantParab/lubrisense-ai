"""Phase 27 focused failure-degradation tests — deliberately not a chaos-testing
platform (brief §27.12: "focused controlled tests"). ML-unavailable and state-
estimation-unavailable degradation are already exercised throughout
`tests/condition_intelligence/test_condition_engine.py` (every test there runs with no
`MLInferenceResult`/`StateEstimate` present at all — structurally identical to "ML/state
unavailable" from `ConditionEngine`'s perspective) and RAG/LLM-unavailable degradation is
already covered by `tests/knowledge/test_retrieval.py`
(`INSUFFICIENT_DOCUMENTATION_TEXT`), `tests/agent/test_agent_service.py`, and
`tests/test_resilience.py` (the LLM-provider circuit breaker). This file covers the
remaining gaps: CMMS adapter failure isolation, and a generic-unhandled-exception clean
error envelope (the practical, non-disruptive proxy for "the database becomes
unavailable mid-request" against this session's shared Postgres — see
docs/RESILIENCE.md)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.cmms.domain.adapter import WorkOrderDraftRequest, WorkOrderRecord
from app.cmms.services.cmms_service import CMMSService, CMMSUnavailableError
from app.domain.enums import (
    DecisionPriority,
    MaintenanceState,
    RecommendedAction,
    RecommendedWindow,
)
from app.domain.models import Incident, MaintenanceCase, Tenant
from tests.factories import (
    make_customer,
    make_machine,
    make_plant,
    make_production_line,
    make_site,
    make_tenant,
)


class _AlwaysFailingCMMSAdapter:
    async def create_work_order_draft(self, request: WorkOrderDraftRequest) -> WorkOrderRecord:
        del request
        raise ConnectionError("simulated CMMS outage")

    async def get_work_order(self, external_reference: str) -> WorkOrderRecord | None:
        del external_reference
        raise ConnectionError("simulated CMMS outage")

    async def update_work_order_status(
        self, external_reference: str, status: str
    ) -> WorkOrderRecord:
        raise ConnectionError("simulated CMMS outage")

    async def add_note(self, external_reference: str, note: str) -> None:
        raise ConnectionError("simulated CMMS outage")


async def _committed_case(session: AsyncSession, tenant: Tenant) -> MaintenanceCase:
    from datetime import UTC, datetime

    customer = await make_customer(session, tenant)
    site = await make_site(session, tenant, customer)
    plant = await make_plant(session, tenant, site)
    line = await make_production_line(session, tenant, plant)
    machine = await make_machine(session, tenant, line)
    now = datetime.now(UTC)
    incident = Incident(
        tenant_id=tenant.id,
        machine_id=machine.id,
        correlation_key=f"resilience-{uuid.uuid4()}",
        incident_type="DEVELOPING_RESTRICTION_PATTERN",
        title="Resilience Test Incident",
        summary="Test",
        severity="WARNING",
        priority=DecisionPriority.PLANNED,
        state="OPEN",
        first_detected_at=now,
        last_updated_at=now,
        policy_version="v1",
        engine_version="v1",
    )
    session.add(incident)
    await session.flush()
    case = MaintenanceCase(
        tenant_id=tenant.id,
        incident_id=incident.id,
        machine_id=machine.id,
        condition_assessment_id=uuid.uuid4(),
        decision_assessment_id=uuid.uuid4(),
        recommended_action=RecommendedAction.INSPECT_LUBRICATION_PATH,
        recommended_window=RecommendedWindow.NEXT_PLANNED_MAINTENANCE,
        priority=DecisionPriority.PLANNED,
        state=MaintenanceState.NOT_STARTED,
        checklist=[{"text": "Inspect", "completed": False}],
        checklist_template_id="test",
        policy_version="v1",
    )
    session.add(case)
    await session.flush()
    return case


@pytest.mark.asyncio
async def test_cmms_adapter_failure_isolated_from_maintenance_case(
    db_session: AsyncSession,
) -> None:
    """Phase 20 brief §20.6, reverified for Phase 27 (§27.10): a CMMS adapter failure
    must raise `CMMSUnavailableError` and must never mutate the underlying
    `MaintenanceCase` — core workflow state survives untouched."""
    tenant = await make_tenant(db_session)
    case = await _committed_case(db_session, tenant)
    original_state = case.state
    original_updated_at = case.updated_at

    service = CMMSService(db_session, adapter=_AlwaysFailingCMMSAdapter())
    with pytest.raises(CMMSUnavailableError):
        await service.create_draft(tenant.id, case.id)

    await db_session.refresh(case)
    assert case.state == original_state
    assert case.updated_at == original_updated_at


def test_unhandled_exception_returns_clean_error_envelope_not_a_traceback(
    api_tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The practical, non-disruptive proxy for "a dependency (e.g. the database)
    becomes unavailable mid-request": force an unexpected exception deep in a request
    and confirm the global handler (`app.core.errors.register_exception_handlers`,
    established at Phase 1) returns the same structured JSON envelope as any other
    error — no stack trace, no internal exception text, in the response body. Uses its
    own `TestClient(raise_server_exceptions=False)` (the shared `client` fixture
    re-raises server exceptions into the test process, which is right for every other
    test but defeats the point of this one)."""
    from app.core.config import get_settings
    from app.main import create_app
    from app.repositories.tenant import TenantRepository

    async def _boom(self: TenantRepository, tenant_id: uuid.UUID) -> None:
        del self, tenant_id
        raise ConnectionError("simulated database outage: connection refused")

    monkeypatch.setattr(TenantRepository, "get", _boom)

    get_settings.cache_clear()
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/api/v1/incidents", headers={"X-Tenant-ID": str(api_tenant.id)}
        )

    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "INTERNAL_SERVER_ERROR"
    assert "connection refused" not in body["message"]
    assert "Traceback" not in response.text
    assert "correlation_id" in body
