"""North Star metric (Phase 22 brief §22.1) — real-Postgres integration tests over
`FeedbackRecord`/`MaintenanceCase`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import (
    ConditionSeverity,
    DecisionPriority,
    FeedbackClassification,
    IncidentState,
    MaintenanceState,
    RecommendedWindow,
)
from app.domain.models import FeedbackRecord, Incident, MaintenanceCase, Tenant
from app.product_metrics.north_star import compute_north_star
from tests.factories import (
    make_customer,
    make_machine,
    make_plant,
    make_production_line,
    make_site,
    make_tenant,
)


async def _make_incident(session: AsyncSession, tenant: Tenant) -> Incident:
    customer = await make_customer(session, tenant)
    site = await make_site(session, tenant, customer)
    plant = await make_plant(session, tenant, site)
    line = await make_production_line(session, tenant, plant)
    machine = await make_machine(session, tenant, line)
    now = datetime.now(UTC)
    incident = Incident(
        tenant_id=tenant.id,
        machine_id=machine.id,
        correlation_key=f"test-{uuid.uuid4()}",
        incident_type="DEVELOPING_RESTRICTION_PATTERN",
        title="Test Incident",
        summary="Test",
        severity=ConditionSeverity.WARNING,
        priority=DecisionPriority.PLANNED,
        state=IncidentState.RESOLVED,
        first_detected_at=now,
        last_updated_at=now,
        policy_version="v1",
        engine_version="v1",
    )
    session.add(incident)
    await session.flush()
    return incident


async def _make_case_with_feedback(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    incident: Incident,
    *,
    recommended_window: RecommendedWindow,
    classification: FeedbackClassification,
) -> None:
    now = datetime.now(UTC)
    case = MaintenanceCase(
        tenant_id=tenant_id,
        incident_id=incident.id,
        machine_id=incident.machine_id,
        condition_assessment_id=uuid.uuid4(),
        decision_assessment_id=uuid.uuid4(),
        recommended_action="INSPECT_LUBRICATION_PATH",
        recommended_window=recommended_window,
        priority="PLANNED",
        state=MaintenanceState.COMPLETED,
        checklist=[],
        checklist_template_id="test",
        policy_version="v1",
        completed_at=now,
    )
    session.add(case)
    await session.flush()
    session.add(
        FeedbackRecord(
            tenant_id=tenant_id,
            maintenance_case_id=case.id,
            incident_id=case.incident_id,
            condition_assessment_id=case.condition_assessment_id,
            decision_assessment_id=case.decision_assessment_id,
            classification=classification,
            notes="test",
            recorded_by="test",
            recorded_at=now,
        )
    )
    await session.flush()


@pytest.mark.asyncio
async def test_north_star_undefined_with_no_feedback(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    result = await compute_north_star(db_session, tenant.id)
    assert result.meaningful_issues_total == 0
    assert result.metric.value is None
    assert result.metric.data_completeness_note is not None


@pytest.mark.asyncio
async def test_north_star_counts_true_positive_with_lead_time_in_numerator(
    db_session: AsyncSession,
) -> None:
    tenant = await make_tenant(db_session)
    incident = await _make_incident(db_session, tenant)
    await _make_case_with_feedback(
        db_session,
        tenant.id,
        incident,
        recommended_window=RecommendedWindow.NEXT_PLANNED_MAINTENANCE,
        classification=FeedbackClassification.TRUE_POSITIVE,
    )

    result = await compute_north_star(db_session, tenant.id)

    assert result.meaningful_issues_total == 1
    assert result.meaningful_issues_detected_with_lead_time == 1
    assert result.metric.value == 1.0


@pytest.mark.asyncio
async def test_north_star_excludes_emergency_window_from_numerator(
    db_session: AsyncSession,
) -> None:
    tenant = await make_tenant(db_session)
    incident = await _make_incident(db_session, tenant)
    await _make_case_with_feedback(
        db_session,
        tenant.id,
        incident,
        recommended_window=RecommendedWindow.NOW,
        classification=FeedbackClassification.TRUE_POSITIVE,
    )

    result = await compute_north_star(db_session, tenant.id)

    assert result.meaningful_issues_total == 1
    assert result.meaningful_issues_detected_with_lead_time == 0
    assert result.metric.value == 0.0


@pytest.mark.asyncio
async def test_north_star_includes_missed_failure_in_denominator_only(
    db_session: AsyncSession,
) -> None:
    tenant = await make_tenant(db_session)
    incident = await _make_incident(db_session, tenant)
    await _make_case_with_feedback(
        db_session,
        tenant.id,
        incident,
        recommended_window=RecommendedWindow.NEXT_PLANNED_MAINTENANCE,
        classification=FeedbackClassification.MISSED_FAILURE,
    )

    result = await compute_north_star(db_session, tenant.id)

    assert result.meaningful_issues_total == 1
    assert result.meaningful_issues_detected_with_lead_time == 0


@pytest.mark.asyncio
async def test_north_star_excludes_false_positive_and_inconclusive(
    db_session: AsyncSession,
) -> None:
    tenant = await make_tenant(db_session)
    incident_a = await _make_incident(db_session, tenant)
    incident_b = await _make_incident(db_session, tenant)
    await _make_case_with_feedback(
        db_session,
        tenant.id,
        incident_a,
        recommended_window=RecommendedWindow.NEXT_PLANNED_MAINTENANCE,
        classification=FeedbackClassification.FALSE_POSITIVE,
    )
    await _make_case_with_feedback(
        db_session,
        tenant.id,
        incident_b,
        recommended_window=RecommendedWindow.NEXT_PLANNED_MAINTENANCE,
        classification=FeedbackClassification.INCONCLUSIVE,
    )

    result = await compute_north_star(db_session, tenant.id)

    assert result.meaningful_issues_total == 0
