"""`QualityQueryService.list_fleet_sensor_records` — the fleet-wide read model added for
the Data Quality product rebuild. `GET /issues` alone cannot represent a fully trusted
sensor (it only ever has issue rows for sensors with an actual problem); this is the read
model that answers "every sensor this tenant has evaluated", trusted or not."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_quality.domain.results import RuleIssue
from app.data_quality.repositories.quality_assessment_repository import (
    QualityAssessmentRepository,
)
from app.data_quality.repositories.quality_issue_repository import QualityIssueRepository
from app.data_quality.repositories.sensor_quality_state_repository import (
    SensorQualityStateRepository,
)
from app.data_quality.services.quality_query_service import QualityQueryService
from app.domain.enums import (
    Eligibility,
    IssueSeverity,
    QualityDimension,
    QualityIssueType,
    QualityState,
    SensorType,
)
from tests.rules_engine.helpers import build_machine_with_topology, make_topology_sensor


async def _mark(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    machine_id: uuid.UUID,
    sensor_id: uuid.UUID,
    *,
    quality_state: QualityState,
    eligibility: Eligibility,
) -> None:
    await SensorQualityStateRepository(session).upsert(
        tenant_id,
        sensor_id,
        machine_id=machine_id,
        quality_state=quality_state,
        eligibility=eligibility,
        last_observed_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_trusted_sensor_with_no_issue_is_listed(db_session: AsyncSession) -> None:
    tenant, machine, _system, _circuit, _bearing = await build_machine_with_topology(db_session)
    sensor = await make_topology_sensor(
        db_session, tenant, SensorType.PRESSURE, machine_id=machine.id
    )
    await _mark(
        db_session,
        tenant.id,
        machine.id,
        sensor.id,
        quality_state=QualityState.TRUSTED,
        eligibility=Eligibility.ELIGIBLE,
    )

    service = QualityQueryService(db_session)
    records = await service.list_fleet_sensor_records(tenant.id)

    assert len(records) == 1
    record = records[0]
    assert record.sensor.id == sensor.id
    assert record.state.quality_state == QualityState.TRUSTED
    assert record.active_issues == []
    # PRESSURE's expected cadence in `demo_quality_policy.yaml` — a real policy value, not
    # a fabricated one.
    assert record.expected_reporting_interval_seconds == 10.0


@pytest.mark.asyncio
async def test_unusable_sensor_includes_its_active_issue(db_session: AsyncSession) -> None:
    tenant, machine, _system, _circuit, _bearing = await build_machine_with_topology(db_session)
    sensor = await make_topology_sensor(
        db_session, tenant, SensorType.VIBRATION_RMS, machine_id=machine.id
    )
    await _mark(
        db_session,
        tenant.id,
        machine.id,
        sensor.id,
        quality_state=QualityState.UNUSABLE,
        eligibility=Eligibility.INELIGIBLE,
    )
    now = datetime.now(UTC)
    assessment = await QualityAssessmentRepository(db_session).create_window_assessment(
        tenant_id=tenant.id,
        sensor_id=sensor.id,
        machine_id=machine.id,
        window_start=now - timedelta(hours=1),
        window_end=now,
        quality_state=QualityState.UNUSABLE,
        policy_version="1",
        rule_versions={"sensor_drift_suspected": "1"},
        metadata={},
    )
    issue = RuleIssue(
        dimension=QualityDimension.SENSOR_HEALTH,
        issue_type=QualityIssueType.SENSOR_DRIFT_SUSPECTED,
        severity=IssueSeverity.ERROR,
        message="sustained drift suspected",
        rule_id="sensor_drift_suspected",
        rule_version="1",
        evidence={},
        window_start=now - timedelta(hours=1),
        window_end=now,
    )
    await QualityIssueRepository(db_session).upsert_active_window_issue(
        tenant_id=tenant.id,
        sensor_id=sensor.id,
        machine_id=machine.id,
        assessment_id=assessment.id,
        issue=issue,
        policy_version="1",
    )

    service = QualityQueryService(db_session)
    records = await service.list_fleet_sensor_records(tenant.id)

    assert len(records) == 1
    assert len(records[0].active_issues) == 1
    assert records[0].active_issues[0].issue_type == QualityIssueType.SENSOR_DRIFT_SUSPECTED


@pytest.mark.asyncio
async def test_filters_by_machine_and_quality_state(db_session: AsyncSession) -> None:
    tenant, machine_a, _s1, _c1, _b1 = await build_machine_with_topology(db_session)
    _tenant2, machine_b, _s2, _c2, _b2 = await build_machine_with_topology(db_session)
    # Reuse the same tenant for both machines so this is a same-tenant, cross-machine
    # filter test, not a tenant-isolation test.
    sensor_a = await make_topology_sensor(
        db_session, tenant, SensorType.RPM, machine_id=machine_a.id
    )
    sensor_b = await make_topology_sensor(
        db_session, tenant, SensorType.RPM, machine_id=machine_a.id
    )
    await _mark(
        db_session,
        tenant.id,
        machine_a.id,
        sensor_a.id,
        quality_state=QualityState.TRUSTED,
        eligibility=Eligibility.ELIGIBLE,
    )
    await _mark(
        db_session,
        tenant.id,
        machine_a.id,
        sensor_b.id,
        quality_state=QualityState.USABLE_WITH_CAUTION,
        eligibility=Eligibility.ELIGIBLE_WITH_CAUTION,
    )

    service = QualityQueryService(db_session)

    only_caution = await service.list_fleet_sensor_records(
        tenant.id, quality_state=QualityState.USABLE_WITH_CAUTION
    )
    assert [r.sensor.id for r in only_caution] == [sensor_b.id]

    for_other_machine = await service.list_fleet_sensor_records(tenant.id, machine_id=machine_b.id)
    assert for_other_machine == []


@pytest.mark.asyncio
async def test_resolved_event_issue_is_not_active(db_session: AsyncSession) -> None:
    """An event-scoped issue is created directly as RESOLVED (Phase 7 — it is an
    immutable fact about one past event, not an ongoing condition). It must never show up
    as an *active* issue on the fleet-wide record."""
    tenant, machine, _system, _circuit, _bearing = await build_machine_with_topology(db_session)
    sensor = await make_topology_sensor(
        db_session, tenant, SensorType.PRESSURE, machine_id=machine.id
    )
    await _mark(
        db_session,
        tenant.id,
        machine.id,
        sensor.id,
        quality_state=QualityState.TRUSTED,
        eligibility=Eligibility.ELIGIBLE,
    )
    assessment = await QualityAssessmentRepository(db_session).create_event_assessment(
        tenant_id=tenant.id,
        sensor_id=sensor.id,
        machine_id=machine.id,
        event_id=uuid.uuid4(),
        quality_state=QualityState.TRUSTED,
        policy_version="1",
        rule_versions={"out_of_order": "1"},
        metadata={},
    )
    issue = RuleIssue(
        dimension=QualityDimension.ORDERING,
        issue_type=QualityIssueType.OUT_OF_ORDER,
        severity=IssueSeverity.INFO,
        message="reordered under burst",
        rule_id="out_of_order",
        rule_version="1",
        evidence={},
        event_id=assessment.event_id,
    )
    await QualityIssueRepository(db_session).create_event_issue(
        tenant_id=tenant.id,
        sensor_id=sensor.id,
        machine_id=machine.id,
        assessment_id=assessment.id,
        issue=issue,
        policy_version="1",
    )

    service = QualityQueryService(db_session)
    records = await service.list_fleet_sensor_records(tenant.id)

    assert len(records) == 1
    assert records[0].active_issues == []


@pytest.mark.asyncio
async def test_tenant_isolation(db_session: AsyncSession) -> None:
    tenant_a, machine_a, _s1, _c1, _b1 = await build_machine_with_topology(db_session)
    tenant_b, machine_b, _s2, _c2, _b2 = await build_machine_with_topology(db_session)
    sensor_a = await make_topology_sensor(
        db_session, tenant_a, SensorType.PRESSURE, machine_id=machine_a.id
    )
    sensor_b = await make_topology_sensor(
        db_session, tenant_b, SensorType.PRESSURE, machine_id=machine_b.id
    )
    await _mark(
        db_session,
        tenant_a.id,
        machine_a.id,
        sensor_a.id,
        quality_state=QualityState.TRUSTED,
        eligibility=Eligibility.ELIGIBLE,
    )
    await _mark(
        db_session,
        tenant_b.id,
        machine_b.id,
        sensor_b.id,
        quality_state=QualityState.TRUSTED,
        eligibility=Eligibility.ELIGIBLE,
    )

    service = QualityQueryService(db_session)
    records = await service.list_fleet_sensor_records(tenant_a.id)

    assert [r.sensor.id for r in records] == [sensor_a.id]
