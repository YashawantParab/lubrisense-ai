"""Database integration: `CMMSService` — draft creation from a real `MaintenanceCase`,
idempotency, and CMMS-failure isolation (Phase 20 brief §20.5/§20.6, "CMMS RESILIENCE
TEST": incident/workflow must persist and be retryable when the adapter fails)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.cmms.domain.adapter import WorkOrderDraftRequest, WorkOrderRecord
from app.cmms.services.cmms_service import CMMSService, CMMSUnavailableError
from app.domain.enums import RuleFindingSeverity, RuleFindingType, SensorType
from app.domain.models import Incident, MaintenanceCase, Tenant
from app.incidents.services.incident_service import IncidentService
from app.maintenance.services.maintenance_service import MaintenanceService
from tests.incidents.helpers import active_rule_finding
from tests.rules_engine.helpers import build_machine_with_topology, make_topology_sensor


class _FailingAdapter:
    async def create_work_order_draft(self, request: WorkOrderDraftRequest) -> WorkOrderRecord:
        del request
        raise ConnectionError("simulated CMMS outage")

    async def get_work_order(self, external_reference: str) -> WorkOrderRecord | None:
        del external_reference
        raise ConnectionError("simulated CMMS outage")

    async def update_work_order_status(
        self, external_reference: str, status: str
    ) -> WorkOrderRecord:
        raise NotImplementedError

    async def add_note(self, external_reference: str, note: str) -> None:
        raise NotImplementedError


async def _case_ready_for_a_draft(
    db_session: AsyncSession,
) -> tuple[Tenant, MaintenanceCase, Incident]:
    tenant, machine, _system, circuit, _bearing = await build_machine_with_topology(db_session)
    await make_topology_sensor(db_session, tenant, SensorType.PRESSURE, circuit_id=circuit.id)
    await active_rule_finding(
        db_session,
        tenant_id=tenant.id,
        machine_id=machine.id,
        finding_type=RuleFindingType.FLOW_PRESSURE_RESTRICTION_PATTERN,
        severity=RuleFindingSeverity.WARNING,
    )
    incidents = IncidentService(db_session)
    incident = await incidents.evaluate_machine(tenant.id, machine.id)
    assert incident is not None
    await incidents.acknowledge(tenant.id, incident.id)
    await incidents.start_investigation(tenant.id, incident.id)
    maintenance = MaintenanceService(db_session)
    case = await maintenance.create_case_for_incident(tenant.id, incident.id)
    return tenant, case, incident


@pytest.mark.asyncio
async def test_create_draft_from_a_real_maintenance_case(db_session: AsyncSession) -> None:
    tenant, case, _incident = await _case_ready_for_a_draft(db_session)
    service = CMMSService(db_session)
    record = await service.create_draft(tenant.id, case.id)
    assert record.status == "DRAFT"
    assert record.external_reference.startswith("DEMO-WO-")
    assert record.priority == case.priority.value


@pytest.mark.asyncio
async def test_create_draft_is_idempotent_via_the_service(db_session: AsyncSession) -> None:
    tenant, case, _incident = await _case_ready_for_a_draft(db_session)
    service = CMMSService(db_session)
    first = await service.create_draft(tenant.id, case.id)
    second = await service.create_draft(tenant.id, case.id)
    assert first.external_reference == second.external_reference


@pytest.mark.asyncio
async def test_cmms_failure_is_isolated_and_case_remains_usable(db_session: AsyncSession) -> None:
    """Mandatory "CMMS RESILIENCE TEST": simulate a DemoCMMS failure and verify the
    maintenance case/incident persist untouched, and the draft can be retried once the
    adapter is available again."""
    tenant, case, incident = await _case_ready_for_a_draft(db_session)
    failing_service = CMMSService(db_session, adapter=_FailingAdapter())

    with pytest.raises(CMMSUnavailableError):
        await failing_service.create_draft(tenant.id, case.id)

    # Core workflow state is completely untouched by the CMMS failure.
    maintenance = MaintenanceService(db_session)
    case_after_failure = await maintenance.get(tenant.id, case.id)
    assert case_after_failure.state.value == case.state.value

    incidents = IncidentService(db_session)
    incident_after_failure = await incidents.get(tenant.id, incident.id)
    assert incident_after_failure.state.value == incident.state.value

    # Retry with a working adapter succeeds — the failure was not permanent/fatal.
    working_service = CMMSService(db_session)
    record = await working_service.create_draft(tenant.id, case.id)
    assert record.status == "DRAFT"


@pytest.mark.asyncio
async def test_get_work_order_failure_is_isolated(db_session: AsyncSession) -> None:
    tenant, _case, _incident = await _case_ready_for_a_draft(db_session)
    failing_service = CMMSService(db_session, adapter=_FailingAdapter())
    with pytest.raises(CMMSUnavailableError):
        await failing_service.get_work_order(tenant.id, "DEMO-WO-ANYTHING")
