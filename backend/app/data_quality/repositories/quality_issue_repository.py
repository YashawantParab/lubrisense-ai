"""Persistence for `QualityIssue`, including the two idempotency keys and the
ACTIVE/RECOVERING/RESOLVED lifecycle for window-scoped issues (Phase 7 brief §31/§33/§49;
plan decision #8).

Event-scoped issues are immutable facts about one past event: inserted directly as
`RESOLVED`, idempotent via `ON CONFLICT DO NOTHING` on `uq_quality_issue_event_scope` — a
reprocessing run under the same `rule_version` is a safe no-op.

Window-scoped issues represent an ongoing condition: upserted via `ON CONFLICT DO UPDATE`
against the partial unique index `uq_quality_issue_active_window_scope` (only one row may
be ACTIVE/RECOVERING per `(tenant, sensor, rule_id, rule_version)` at a time — see
`5257a5e8e595`'s migration comment for why a plain constraint on sliding window bounds would
have created a new row every evaluation cycle instead of evolving one).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_quality.domain.results import RuleIssue
from app.domain.enums import IssueSeverity, IssueStatus
from app.domain.models import QualityIssue

_ACTIVE_WINDOW_INDEX_ELEMENTS = ("tenant_id", "sensor_id", "rule_id", "rule_version")
_ACTIVE_STATUSES = (IssueStatus.ACTIVE, IssueStatus.RECOVERING)

# Real bug found in Phase 35 comprehensive testing: Postgres's ON CONFLICT partial-index
# arbiter match requires the predicate to be a *constant-foldable* expression, identical
# to the index's own stored predicate — a bind-parameterized `.in_([...])` (what
# `QualityIssue.__table__.c.status.in_([s.value for s in _ACTIVE_STATUSES])` compiles to)
# can only be evaluated at execution time, so Postgres cannot statically verify it matches
# `uq_quality_issue_active_window_scope`'s predicate and raises `InvalidColumnReference:
# there is no unique or exclusion constraint matching the ON CONFLICT specification` on
# every single upsert. `_ACTIVE_STATUSES` is a fixed internal enum (never user input), so
# inlining the values as SQL literals via `text()` is safe and is the standard fix for
# this exact SQLAlchemy + Postgres partial-index-upsert limitation.
_ACTIVE_WINDOW_INDEX_WHERE = text(
    "status IN (" + ", ".join(f"'{status.value}'" for status in _ACTIVE_STATUSES) + ")"
)


class QualityIssueRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_event_issue(
        self,
        *,
        tenant_id: uuid.UUID,
        sensor_id: uuid.UUID,
        machine_id: uuid.UUID | None,
        assessment_id: uuid.UUID,
        issue: RuleIssue,
        policy_version: str,
    ) -> None:
        now = datetime.now(UTC)
        stmt = (
            pg_insert(QualityIssue.__table__)  # type: ignore[arg-type]
            .values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                sensor_id=sensor_id,
                machine_id=machine_id,
                assessment_id=assessment_id,
                dimension=issue.dimension,
                issue_type=issue.issue_type,
                severity=issue.severity,
                status=IssueStatus.RESOLVED,
                message=issue.message,
                evidence=issue.evidence,
                affected_event_ids=issue.affected_event_ids or [str(issue.event_id)],
                event_id=issue.event_id,
                window_start=None,
                window_end=None,
                first_seen=now,
                last_seen=now,
                resolved_at=now,
                rule_id=issue.rule_id,
                rule_version=issue.rule_version,
                policy_version=policy_version,
            )
            .on_conflict_do_nothing(constraint="uq_quality_issue_event_scope")
        )
        await self.session.execute(stmt)

    async def upsert_active_window_issue(
        self,
        *,
        tenant_id: uuid.UUID,
        sensor_id: uuid.UUID,
        machine_id: uuid.UUID | None,
        assessment_id: uuid.UUID,
        issue: RuleIssue,
        policy_version: str,
    ) -> None:
        """Called when a window-level rule fires. Creates the row on first detection;
        re-firing on a later evaluation cycle updates the same row in place (extends
        `last_seen`, refreshes evidence) and resets `RECOVERING` back to `ACTIVE` — the
        condition is still present, so it never actually recovered."""
        now = datetime.now(UTC)
        insert_values = {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "sensor_id": sensor_id,
            "machine_id": machine_id,
            "assessment_id": assessment_id,
            "dimension": issue.dimension,
            "issue_type": issue.issue_type,
            "severity": issue.severity,
            "status": IssueStatus.ACTIVE,
            "message": issue.message,
            "evidence": issue.evidence,
            "affected_event_ids": issue.affected_event_ids,
            "event_id": None,
            "window_start": issue.window_start,
            "window_end": issue.window_end,
            "first_seen": now,
            "last_seen": now,
            "resolved_at": None,
            "rule_id": issue.rule_id,
            "rule_version": issue.rule_version,
            "policy_version": policy_version,
        }
        stmt = pg_insert(QualityIssue.__table__).values(**insert_values)  # type: ignore[arg-type]
        stmt = stmt.on_conflict_do_update(
            index_elements=_ACTIVE_WINDOW_INDEX_ELEMENTS,
            # Must be a literal (not bind-parameterized) predicate matching the partial
            # index's own stored predicate for Postgres to select it as the ON CONFLICT
            # arbiter — see `_ACTIVE_WINDOW_INDEX_WHERE`'s comment above.
            index_where=_ACTIVE_WINDOW_INDEX_WHERE,
            set_={
                "assessment_id": assessment_id,
                "status": IssueStatus.ACTIVE,
                "severity": issue.severity,
                "message": issue.message,
                "evidence": issue.evidence,
                "affected_event_ids": issue.affected_event_ids,
                "window_start": issue.window_start,
                "window_end": issue.window_end,
                "last_seen": now,
                "policy_version": policy_version,
            },
        )
        await self.session.execute(stmt)

    async def advance_or_resolve_if_absent(
        self,
        *,
        tenant_id: uuid.UUID,
        sensor_id: uuid.UUID,
        rule_id: str,
        rule_version: str,
    ) -> None:
        """Called when a window-level rule does NOT fire for a sensor this cycle.
        ACTIVE -> RECOVERING on the first clean cycle, RECOVERING -> RESOLVED on the next —
        requires two consecutive clean evaluations before a condition is called resolved,
        avoiding flapping on one borderline window."""
        existing = await self.session.scalar(
            select(QualityIssue).where(
                QualityIssue.tenant_id == tenant_id,
                QualityIssue.sensor_id == sensor_id,
                QualityIssue.rule_id == rule_id,
                QualityIssue.rule_version == rule_version,
                QualityIssue.status.in_(_ACTIVE_STATUSES),
            )
        )
        if existing is None:
            return
        now = datetime.now(UTC)
        if existing.status == IssueStatus.ACTIVE:
            await self.session.execute(
                update(QualityIssue)
                .where(QualityIssue.id == existing.id)
                .values(status=IssueStatus.RECOVERING, last_seen=now)
            )
        else:
            await self.session.execute(
                update(QualityIssue)
                .where(QualityIssue.id == existing.id)
                .values(status=IssueStatus.RESOLVED, resolved_at=now, last_seen=now)
            )

    async def list_active_severities(
        self, tenant_id: uuid.UUID, sensor_id: uuid.UUID
    ) -> list[IssueSeverity]:
        stmt = select(QualityIssue.severity).where(
            QualityIssue.tenant_id == tenant_id,
            QualityIssue.sensor_id == sensor_id,
            QualityIssue.status.in_(_ACTIVE_STATUSES),
        )
        result = await self.session.execute(stmt)
        return [row[0] for row in result.all()]

    async def count_active(self, tenant_id: uuid.UUID, sensor_id: uuid.UUID) -> int:
        return len(await self.list_active_severities(tenant_id, sensor_id))

    async def list_active_for_sensors(
        self, tenant_id: uuid.UUID, sensor_ids: Iterable[uuid.UUID]
    ) -> list[QualityIssue]:
        """Bulk ACTIVE/RECOVERING lookup for a known set of sensors — the fleet-wide
        sensor read model (`QualityQueryService.list_fleet_sensor_records`) needs every
        tracked sensor's current issue(s) without one query per sensor."""
        ids = list(sensor_ids)
        if not ids:
            return []
        stmt = (
            select(QualityIssue)
            .where(
                QualityIssue.tenant_id == tenant_id,
                QualityIssue.sensor_id.in_(ids),
                QualityIssue.status.in_(_ACTIVE_STATUSES),
            )
            .order_by(QualityIssue.last_seen.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_active_by_severity(self, tenant_id: uuid.UUID) -> dict[str, int]:
        stmt = (
            select(QualityIssue.severity, func.count())
            .where(QualityIssue.tenant_id == tenant_id, QualityIssue.status.in_(_ACTIVE_STATUSES))
            .group_by(QualityIssue.severity)
        )
        result = await self.session.execute(stmt)
        return {severity.value: count for severity, count in result.all()}

    async def list_issues(
        self,
        tenant_id: uuid.UUID,
        *,
        sensor_id: uuid.UUID | None = None,
        machine_id: uuid.UUID | None = None,
        severity: IssueSeverity | None = None,
        status: IssueStatus | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> list[QualityIssue]:
        clauses: list[Any] = [QualityIssue.tenant_id == tenant_id]
        if sensor_id is not None:
            clauses.append(QualityIssue.sensor_id == sensor_id)
        if machine_id is not None:
            clauses.append(QualityIssue.machine_id == machine_id)
        if severity is not None:
            clauses.append(QualityIssue.severity == severity)
        if status is not None:
            clauses.append(QualityIssue.status == status)
        if start is not None:
            clauses.append(QualityIssue.last_seen >= start)
        if end is not None:
            clauses.append(QualityIssue.last_seen <= end)
        stmt = (
            select(QualityIssue)
            .where(*clauses)
            .order_by(QualityIssue.last_seen.desc())
            .limit(min(limit, 2000))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
