"""Proves `scripts/export_feedback_provenance.py`'s `_export()` correctly joins a
`FeedbackRecord` to its `ConditionAssessment` and surfaces the ML/rule/state-estimate
evidence ids that assessment cited — read-only, no mutation, per Phase 32 brief §32.7.

Reuses the real Phase 17 `MaintenanceService` full workflow (the same pattern as
`tests/maintenance/test_maintenance_service.py`) rather than hand-constructing rows, so
the `FeedbackRecord`/`ConditionAssessment` pair is exactly what a real technician
feedback loop produces."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import (
    FeedbackClassification,
    RuleFindingSeverity,
    RuleFindingType,
    SensorType,
)
from app.incidents.services.incident_service import IncidentService
from app.maintenance.services.maintenance_service import MaintenanceService
from scripts.export_feedback_provenance import _export
from tests.incidents.helpers import active_rule_finding
from tests.rules_engine.helpers import build_machine_with_topology, make_topology_sensor


@pytest.mark.asyncio
async def test_export_links_feedback_to_condition_evidence(db_session: AsyncSession) -> None:
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
    await maintenance.plan(tenant.id, case.id, planned_for=None)
    await maintenance.start(tenant.id, case.id)
    await maintenance.complete(
        tenant.id,
        case.id,
        classification=FeedbackClassification.TRUE_POSITIVE,
        confirmed_component="distributor",
        confirmed_finding="Partially blocked distributor outlet.",
        notes="Confirmed and cleared.",
        recorded_by="demo-technician",
    )

    report = await _export(db_session, tenant.id)

    assert len(report) == 1
    entry = report[0]
    assert entry["classification"] == "TRUE_POSITIVE"
    assert entry["condition_assessment_id"] == str(case.condition_assessment_id)
    assert isinstance(entry["ml_result_ids"], list)
    assert isinstance(entry["rule_finding_ids"], list)
    assert entry["rule_finding_ids"], "the rule-evaluated incident must cite its rule finding"
    assert entry["note"].startswith("Provenance only")


@pytest.mark.asyncio
async def test_export_returns_empty_list_for_tenant_with_no_feedback(
    db_session: AsyncSession,
) -> None:
    report = await _export(db_session, uuid.uuid4())
    assert report == []
