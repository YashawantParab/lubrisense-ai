"""Database integration: `MaintenanceService` against real Postgres — case creation
idempotency, the full plan/start/finding/action/complete workflow, and the technician
feedback loop (Phase 17 brief)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import (
    FeedbackClassification,
    MaintenanceActionType,
    RuleFindingSeverity,
    RuleFindingType,
    SensorType,
    TechnicianFindingResult,
)
from app.domain.models import Incident, Machine, Tenant
from app.incidents.services.incident_service import IncidentService
from app.maintenance.services.maintenance_service import (
    InvalidMaintenanceTransitionError,
    MaintenanceCaseNotFoundError,
    MaintenanceService,
)
from tests.incidents.helpers import active_rule_finding
from tests.rules_engine.helpers import build_machine_with_topology, make_topology_sensor


async def _restriction_incident(
    db_session: AsyncSession,
) -> tuple[Tenant, Machine, Incident]:
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
    return tenant, machine, incident


@pytest.mark.asyncio
async def test_create_case_for_incident_is_idempotent(db_session: AsyncSession) -> None:
    tenant, _machine, incident = await _restriction_incident(db_session)
    service = MaintenanceService(db_session)
    first = await service.create_case_for_incident(tenant.id, incident.id)
    second = await service.create_case_for_incident(tenant.id, incident.id)
    assert first.id == second.id


@pytest.mark.asyncio
async def test_case_created_with_a_real_checklist_from_the_recommended_action(
    db_session: AsyncSession,
) -> None:
    tenant, _machine, incident = await _restriction_incident(db_session)
    service = MaintenanceService(db_session)
    case = await service.create_case_for_incident(tenant.id, incident.id)
    assert case.recommended_action.value in ("INSPECT_LUBRICATION_PATH", "INSPECT_DISTRIBUTOR")
    assert len(case.checklist) > 0
    assert all("text" in item and "completed" in item for item in case.checklist)
    assert case.condition_assessment_id is not None
    assert case.decision_assessment_id is not None


@pytest.mark.asyncio
async def test_full_workflow_plan_start_finding_action_complete(db_session: AsyncSession) -> None:
    tenant, _machine, incident = await _restriction_incident(db_session)
    service = MaintenanceService(db_session)
    case = await service.create_case_for_incident(tenant.id, incident.id)

    planned = await service.plan(tenant.id, case.id, planned_for=None)
    assert planned.state.value == "PLANNED"

    started = await service.start(tenant.id, case.id)
    assert started.state.value == "IN_PROGRESS"
    assert started.started_at is not None

    finding = await service.record_finding(
        tenant.id,
        case.id,
        result=TechnicianFindingResult.PARTIALLY_CONFIRMED,
        component="distributor",
        observed_issue="Partially blocked distributor outlet (synthetic demo finding).",
        notes="Demo technician inspection.",
        technician_identifier="demo-technician",
    )
    assert finding.result.value == "PARTIALLY_CONFIRMED"

    action = await service.record_action(
        tenant.id,
        case.id,
        action_type=MaintenanceActionType.CLEANED,
        notes="Cleaned distributor outlet (synthetic demo action).",
        recorded_by="demo-technician",
    )
    assert action.action_type.value == "CLEANED"

    awaiting = await service.get(tenant.id, case.id)
    assert awaiting.state.value == "AWAITING_VERIFICATION"

    completed = await service.complete(
        tenant.id,
        case.id,
        classification=FeedbackClassification.TRUE_POSITIVE,
        confirmed_component="distributor",
        confirmed_finding="Partially blocked distributor outlet.",
        notes="Confirmed and cleared.",
        recorded_by="demo-technician",
    )
    assert completed.state.value == "COMPLETED"
    assert completed.feedback_classification is not None
    assert completed.feedback_classification.value == "TRUE_POSITIVE"
    assert completed.completed_at is not None

    feedback = await service.get_feedback(tenant.id, case.id)
    assert feedback is not None
    assert feedback.classification.value == "TRUE_POSITIVE"
    assert feedback.post_action_condition_type is not None
    # Phase 17 brief §17.10: the original evidence is never erased, even for a completed
    # case with a confirmed finding.
    assert feedback.condition_assessment_id == case.condition_assessment_id
    assert feedback.decision_assessment_id == case.decision_assessment_id

    incidents = IncidentService(db_session)
    refreshed_incident = await incidents.get(tenant.id, incident.id)
    assert refreshed_incident.state.value == "RESOLVED"


@pytest.mark.asyncio
async def test_false_positive_preserves_original_evidence(db_session: AsyncSession) -> None:
    """Phase 17 brief §17.10: a FALSE_POSITIVE finding must never erase the original
    intelligence result."""
    tenant, _machine, incident = await _restriction_incident(db_session)
    service = MaintenanceService(db_session)
    case = await service.create_case_for_incident(tenant.id, incident.id)
    await service.plan(tenant.id, case.id, planned_for=None)
    await service.start(tenant.id, case.id)
    await service.record_finding(
        tenant.id,
        case.id,
        result=TechnicianFindingResult.NOT_CONFIRMED,
        component=None,
        observed_issue=None,
        notes="No issue found on inspection.",
        technician_identifier="demo-technician",
    )
    await service.record_action(
        tenant.id,
        case.id,
        action_type=MaintenanceActionType.NO_ACTION_REQUIRED,
        notes="No action required.",
        recorded_by="demo-technician",
    )
    completed = await service.complete(
        tenant.id,
        case.id,
        classification=FeedbackClassification.FALSE_POSITIVE,
        notes="No real issue found.",
        recorded_by="demo-technician",
    )
    assert completed.feedback_classification is not None
    assert completed.feedback_classification.value == "FALSE_POSITIVE"
    # Original condition/decision references still resolve to real, untouched rows.
    assert completed.condition_assessment_id is not None
    assert completed.decision_assessment_id is not None


@pytest.mark.asyncio
async def test_different_issue_found_is_a_distinct_finding_result(db_session: AsyncSession) -> None:
    """Phase 17 brief §17.12: technician findings are not forced into TP/FP only."""
    tenant, _machine, incident = await _restriction_incident(db_session)
    service = MaintenanceService(db_session)
    case = await service.create_case_for_incident(tenant.id, incident.id)
    await service.plan(tenant.id, case.id, planned_for=None)
    await service.start(tenant.id, case.id)
    finding = await service.record_finding(
        tenant.id,
        case.id,
        result=TechnicianFindingResult.DIFFERENT_ISSUE_FOUND,
        component="reservoir",
        observed_issue="Reservoir level low (unrelated synthetic demo finding).",
        notes="Different issue than expected.",
        technician_identifier="demo-technician",
    )
    assert finding.result.value == "DIFFERENT_ISSUE_FOUND"


@pytest.mark.asyncio
async def test_starting_a_case_that_is_not_planned_is_rejected(db_session: AsyncSession) -> None:
    tenant, _machine, incident = await _restriction_incident(db_session)
    service = MaintenanceService(db_session)
    case = await service.create_case_for_incident(tenant.id, incident.id)
    with pytest.raises(InvalidMaintenanceTransitionError):
        await service.start(tenant.id, case.id)


@pytest.mark.asyncio
async def test_completing_a_case_without_recording_an_action_still_requires_progress_state(
    db_session: AsyncSession,
) -> None:
    tenant, _machine, incident = await _restriction_incident(db_session)
    service = MaintenanceService(db_session)
    case = await service.create_case_for_incident(tenant.id, incident.id)
    with pytest.raises(InvalidMaintenanceTransitionError):
        await service.complete(
            tenant.id,
            case.id,
            classification=FeedbackClassification.INCONCLUSIVE,
            notes="",
            recorded_by="demo-technician",
        )


@pytest.mark.asyncio
async def test_cancel_a_case(db_session: AsyncSession) -> None:
    tenant, _machine, incident = await _restriction_incident(db_session)
    service = MaintenanceService(db_session)
    case = await service.create_case_for_incident(tenant.id, incident.id)
    cancelled = await service.cancel(tenant.id, case.id, reason="No longer needed.")
    assert cancelled.state.value == "CANCELLED"


@pytest.mark.asyncio
async def test_get_unknown_case_raises(db_session: AsyncSession) -> None:
    import uuid

    service = MaintenanceService(db_session)
    with pytest.raises(MaintenanceCaseNotFoundError):
        await service.get(uuid.uuid4(), uuid.uuid4())
