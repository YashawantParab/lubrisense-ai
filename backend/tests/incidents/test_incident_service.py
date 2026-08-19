"""Database integration: `IncidentService.evaluate_machine()` against real Postgres —
deduplication, separate-fault correlation, healthy no-spam, and recovery (Phase 16 brief
§16.1/§16.5/§16.10/§16.11, "INCIDENT DEDUPLICATION TEST"/"SEPARATE-FAULT TEST")."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import RuleFindingSeverity, RuleFindingType, SensorType, StateType
from app.incidents.services.incident_service import (
    IncidentService,
    IncidentServiceMachineNotFoundError,
)
from tests.incidents.helpers import (
    active_rule_finding,
    deteriorating_state_estimate,
    stable_state_estimate,
)
from tests.rules_engine.helpers import build_machine_with_topology, make_topology_sensor


@pytest.mark.asyncio
async def test_evaluate_unknown_machine_raises(db_session: AsyncSession) -> None:
    import uuid

    service = IncidentService(db_session)
    with pytest.raises(IncidentServiceMachineNotFoundError):
        await service.evaluate_machine(uuid.uuid4(), uuid.uuid4())


@pytest.mark.asyncio
async def test_healthy_machine_never_creates_an_incident(db_session: AsyncSession) -> None:
    """A fresh/uninstrumented machine is INSUFFICIENT_EVIDENCE, not a fault — must never
    spam an incident (Phase 16 brief §16.1, "HEALTHY CASE")."""
    tenant, machine, _system, _circuit, _bearing = await build_machine_with_topology(db_session)
    service = IncidentService(db_session)
    incident = await service.evaluate_machine(tenant.id, machine.id)
    assert incident is None
    assert await service.list_incidents(tenant.id, machine_id=machine.id) == []


@pytest.mark.asyncio
async def test_repeated_evaluations_of_the_same_restriction_correlate_to_one_incident(
    db_session: AsyncSession,
) -> None:
    """Mandatory "INCIDENT DEDUPLICATION TEST" (Phase 16 brief): repeated Condition/
    Decision evaluations for the same evolving restriction must correlate to one open
    incident, never N incidents for N evaluation cycles."""
    tenant, machine, _system, circuit, _bearing = await build_machine_with_topology(db_session)
    await make_topology_sensor(db_session, tenant, SensorType.PRESSURE, circuit_id=circuit.id)
    await active_rule_finding(
        db_session,
        tenant_id=tenant.id,
        machine_id=machine.id,
        finding_type=RuleFindingType.FLOW_PRESSURE_RESTRICTION_PATTERN,
        severity=RuleFindingSeverity.WARNING,
    )

    service = IncidentService(db_session)
    first = await service.evaluate_machine(tenant.id, machine.id)
    second = await service.evaluate_machine(tenant.id, machine.id)
    third = await service.evaluate_machine(tenant.id, machine.id)

    assert first is not None
    assert second is not None
    assert third is not None
    assert first.id == second.id == third.id

    all_incidents = await service.list_incidents(tenant.id, machine_id=machine.id)
    assert len(all_incidents) == 1
    assert len(third.condition_assessment_ids) == 3
    assert len(third.decision_assessment_ids) == 3

    timeline = await service.timeline(tenant.id, first.id)
    created_events = [e for e in timeline if e.event_type.value == "INCIDENT_CREATED"]
    evidence_events = [e for e in timeline if e.event_type.value == "EVIDENCE_ADDED"]
    assert len(created_events) == 1
    assert len(evidence_events) == 2


@pytest.mark.asyncio
async def test_restriction_and_independent_bearing_remain_separate_incidents(
    db_session: AsyncSession,
) -> None:
    """Mandatory "SEPARATE-FAULT TEST" (Phase 16 brief): a restriction-pattern incident
    and an independent-bearing incident must remain distinct.

    Phase 13's `synthesize()` deliberately treats simultaneous delivery + bearing evidence
    as ONE assessment (the delivery hypothesis, with bearing evidence noted, not a second
    condition_type — brief §13.10/synthesis.py Step 4b), so two independent problems only
    ever appear as two condition_types across two temporally-separate evaluations, not one
    fused assessment. This test seeds them sequentially — resolving the restriction finding
    before introducing bearing evidence — the realistic shape of "two problems, discovered
    at different times" that Phase 16 correlation must still keep as two open incidents.
    """
    from app.domain.enums import RuleFindingState

    tenant, machine, _system, circuit, _bearing = await build_machine_with_topology(db_session)
    await make_topology_sensor(db_session, tenant, SensorType.PRESSURE, circuit_id=circuit.id)
    restriction_finding = await active_rule_finding(
        db_session,
        tenant_id=tenant.id,
        machine_id=machine.id,
        finding_type=RuleFindingType.FLOW_PRESSURE_RESTRICTION_PATTERN,
        severity=RuleFindingSeverity.WARNING,
    )
    service = IncidentService(db_session)
    restriction_incident = await service.evaluate_machine(tenant.id, machine.id)
    assert restriction_incident is not None
    assert restriction_incident.incident_type.value == "DEVELOPING_RESTRICTION_PATTERN"

    restriction_finding.state = RuleFindingState.RESOLVED
    await db_session.flush()
    await deteriorating_state_estimate(
        db_session,
        tenant_id=tenant.id,
        machine_id=machine.id,
        state_type=StateType.BEARING_CONDITION_STATE,
    )
    bearing_incident = await service.evaluate_machine(tenant.id, machine.id)
    assert bearing_incident is not None

    assert bearing_incident.id != restriction_incident.id
    assert bearing_incident.correlation_key != restriction_incident.correlation_key

    # The restriction incident is untouched — a fault-family evaluation never resolves an
    # unrelated open incident (only a genuine NORMAL_OPERATION result does, §16.11).
    open_incidents = await service.list_incidents(tenant.id, machine_id=machine.id)
    open_ids = {i.id for i in open_incidents}
    assert restriction_incident.id in open_ids
    assert bearing_incident.id in open_ids
    assert len(open_incidents) == 2


@pytest.mark.asyncio
async def test_recovery_resolves_open_incident_without_closing_it(db_session: AsyncSession) -> None:
    """Phase 16 brief §16.11: recovery may move an incident toward RESOLVED, but closing
    always requires an explicit human action."""
    tenant, machine, _system, circuit, _bearing = await build_machine_with_topology(db_session)
    await make_topology_sensor(db_session, tenant, SensorType.PRESSURE, circuit_id=circuit.id)
    finding = await active_rule_finding(
        db_session,
        tenant_id=tenant.id,
        machine_id=machine.id,
        finding_type=RuleFindingType.FLOW_PRESSURE_RESTRICTION_PATTERN,
        severity=RuleFindingSeverity.WARNING,
    )
    service = IncidentService(db_session)
    incident = await service.evaluate_machine(tenant.id, machine.id)
    assert incident is not None

    # Recovery: the finding resolves AND a fresh, stable state estimate provides real
    # NORMAL_OPERATION evidence — resolving a finding alone would leave `sources_checked`
    # false (INSUFFICIENT_EVIDENCE), which must NOT resolve an open incident (that would
    # conflate "nothing was checked" with "confirmed healthy").
    from app.domain.enums import RuleFindingState

    finding.state = RuleFindingState.RESOLVED
    await db_session.flush()
    await stable_state_estimate(
        db_session,
        tenant_id=tenant.id,
        machine_id=machine.id,
        state_type=StateType.LUBRICATION_DELIVERY_STATE,
    )

    result = await service.evaluate_machine(tenant.id, machine.id)
    assert result is None

    refreshed = await service.get(tenant.id, incident.id)
    assert refreshed.state.value == "RESOLVED"
    assert refreshed.resolved_at is not None
    assert refreshed.closed_at is None


@pytest.mark.asyncio
async def test_sensor_data_quality_limitation_never_creates_an_incident(
    db_session: AsyncSession,
) -> None:
    """Phase 16 brief "SENSOR / DATA QUALITY CASE": a data-quality limitation must not
    create a false machine-maintenance incident."""
    from app.data_quality.repositories.sensor_quality_state_repository import (
        SensorQualityStateRepository,
    )
    from app.domain.enums import Eligibility, QualityState

    tenant, machine, _system, circuit, _bearing = await build_machine_with_topology(db_session)
    sensor = await make_topology_sensor(
        db_session, tenant, SensorType.PRESSURE, circuit_id=circuit.id
    )
    await SensorQualityStateRepository(db_session).upsert(
        tenant.id,
        sensor.id,
        machine_id=machine.id,
        quality_state=QualityState.UNUSABLE,
        eligibility=Eligibility.INELIGIBLE,
        staleness_status="FRESH",
        clock_status="NORMAL",
        active_issue_count=1,
    )
    await db_session.flush()

    service = IncidentService(db_session)
    incident = await service.evaluate_machine(tenant.id, machine.id)
    assert incident is None
    assert await service.list_incidents(tenant.id, machine_id=machine.id) == []
