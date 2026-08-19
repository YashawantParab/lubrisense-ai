"""Real bug found during Phase 35 comprehensive testing: `upsert_active_window_issue`'s
`ON CONFLICT ... WHERE status IN (...)` used a bind-parameterized predicate, which
Postgres cannot match against the partial unique index `uq_quality_issue_active_window_
scope` (the predicate must be literal/constant-foldable for index-arbiter selection) —
every single call raised `psycopg.errors.InvalidColumnReference`, silently swallowed by
the calling `WindowEvaluator`'s per-sensor exception isolation and (until Phase 35 also
fixed `JSONLogFormatter` to actually surface `extra=` fields) invisible in the logs.
None of the pre-existing `tests/data_quality/test_*.py` files caught this because they
only exercise the pure rule-evaluation functions, never the repository's real SQL
against a live Postgres — this file closes that gap."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_quality.domain.results import RuleIssue
from app.data_quality.repositories.quality_issue_repository import QualityIssueRepository
from app.domain.enums import (
    AssessmentScope,
    IssueSeverity,
    IssueStatus,
    QualityDimension,
    QualityIssueType,
    QualityState,
    SensorType,
)
from app.domain.models import QualityAssessment, QualityIssue, Sensor, Tenant
from tests.rules_engine.helpers import build_machine_with_topology, make_topology_sensor


async def _make_assessment(
    db_session: AsyncSession, tenant: Tenant, sensor: Sensor, machine_id: uuid.UUID
) -> uuid.UUID:
    assessment = QualityAssessment(
        tenant_id=tenant.id,
        scope=AssessmentScope.WINDOW,
        sensor_id=sensor.id,
        machine_id=machine_id,
        quality_state=QualityState.USABLE_WITH_CAUTION,
        policy_version="1",
        rule_versions={"stale_stream": "1"},
    )
    db_session.add(assessment)
    await db_session.flush()
    return assessment.id


def _window_issue(rule_id: str = "stale_stream") -> RuleIssue:
    now = datetime.now(UTC)
    return RuleIssue(
        dimension=QualityDimension.TIMELINESS,
        issue_type=QualityIssueType.STALE_STREAM,
        severity=IssueSeverity.WARNING,
        message="sensor has not reported recently",
        rule_id=rule_id,
        rule_version="1",
        evidence={"age_seconds": 120.0},
        window_start=now - timedelta(minutes=5),
        window_end=now,
    )


@pytest.mark.asyncio
async def test_upsert_active_window_issue_inserts_then_updates_the_same_row(
    db_session: AsyncSession,
) -> None:
    tenant, machine, _system, circuit, _bearing = await build_machine_with_topology(db_session)
    sensor = await make_topology_sensor(db_session, tenant, SensorType.RPM, circuit_id=circuit.id)

    repo = QualityIssueRepository(db_session)
    first_assessment_id = await _make_assessment(db_session, tenant, sensor, machine.id)
    await repo.upsert_active_window_issue(
        tenant_id=tenant.id,
        sensor_id=sensor.id,
        machine_id=machine.id,
        assessment_id=first_assessment_id,
        issue=_window_issue(),
        policy_version="1",
    )
    await db_session.flush()

    count_stmt = select(func.count()).select_from(QualityIssue).where(
        QualityIssue.tenant_id == tenant.id, QualityIssue.sensor_id == sensor.id
    )
    assert (await db_session.scalar(count_stmt)) == 1

    # Re-firing on a later evaluation cycle must update the same row, not insert a
    # second one — this is the whole point of the partial-unique-index upsert.
    second_assessment_id = await _make_assessment(db_session, tenant, sensor, machine.id)
    await repo.upsert_active_window_issue(
        tenant_id=tenant.id,
        sensor_id=sensor.id,
        machine_id=machine.id,
        assessment_id=second_assessment_id,
        issue=_window_issue(),
        policy_version="1",
    )
    await db_session.flush()

    assert (await db_session.scalar(count_stmt)) == 1

    row = (
        await db_session.execute(
            select(QualityIssue).where(
                QualityIssue.tenant_id == tenant.id, QualityIssue.sensor_id == sensor.id
            )
        )
    ).scalar_one()
    assert row.assessment_id == second_assessment_id
    assert row.status == IssueStatus.ACTIVE


@pytest.mark.asyncio
async def test_upsert_resets_recovering_back_to_active(db_session: AsyncSession) -> None:
    tenant, machine, _system, circuit, _bearing = await build_machine_with_topology(db_session)
    sensor = await make_topology_sensor(db_session, tenant, SensorType.RPM, circuit_id=circuit.id)

    repo = QualityIssueRepository(db_session)
    assessment_id = await _make_assessment(db_session, tenant, sensor, machine.id)
    await repo.upsert_active_window_issue(
        tenant_id=tenant.id,
        sensor_id=sensor.id,
        machine_id=machine.id,
        assessment_id=assessment_id,
        issue=_window_issue(),
        policy_version="1",
    )
    await db_session.flush()

    await repo.advance_or_resolve_if_absent(
        tenant_id=tenant.id, sensor_id=sensor.id, rule_id="stale_stream", rule_version="1"
    )
    await db_session.flush()

    recovering_row = (
        await db_session.execute(
            select(QualityIssue).where(
                QualityIssue.tenant_id == tenant.id, QualityIssue.sensor_id == sensor.id
            )
        )
    ).scalar_one()
    assert recovering_row.status == IssueStatus.RECOVERING

    # Firing again while RECOVERING must flip the *same* row back to ACTIVE, not insert
    # a new row — this is exactly the case the partial index's WHERE clause has to match.
    reactivation_assessment_id = await _make_assessment(db_session, tenant, sensor, machine.id)
    await repo.upsert_active_window_issue(
        tenant_id=tenant.id,
        sensor_id=sensor.id,
        machine_id=machine.id,
        assessment_id=reactivation_assessment_id,
        issue=_window_issue(),
        policy_version="1",
    )
    await db_session.flush()

    count_stmt = select(func.count()).select_from(QualityIssue).where(
        QualityIssue.tenant_id == tenant.id, QualityIssue.sensor_id == sensor.id
    )
    assert (await db_session.scalar(count_stmt)) == 1
    # The upsert above runs as raw Core SQL (`pg_insert(...).on_conflict_do_update(...)`),
    # which does not refresh the already-loaded `recovering_row` ORM object in the
    # session's identity map — `populate_existing()` forces this query to overwrite it
    # with the real, current row instead of returning the stale cached attributes.
    reactivated_row = (
        await db_session.execute(
            select(QualityIssue)
            .where(QualityIssue.tenant_id == tenant.id, QualityIssue.sensor_id == sensor.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert reactivated_row.status == IssueStatus.ACTIVE
