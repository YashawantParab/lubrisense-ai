"""Window-level orchestration (Phase 7 brief §6 — the periodic-task half of the
event/window split; plan decision #5).

Stateless and restart-safe: every call queries a fresh time range from
`TelemetryRepository` rather than trusting any in-memory rolling buffer (brief §6's "no
transport-specific state" convention, mirrored from Phase 6). Runs on a separate asyncio
task in the worker, not inline with Kafka message processing.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.data_quality.config.policy import QualityPolicy
from app.data_quality.domain.context import TelemetryPoint
from app.data_quality.domain.results import RuleIssue
from app.data_quality.repositories.quality_assessment_repository import (
    QualityAssessmentRepository,
)
from app.data_quality.repositories.quality_issue_repository import QualityIssueRepository
from app.data_quality.repositories.sensor_quality_state_repository import (
    SensorQualityStateRepository,
)
from app.data_quality.rules.communication import (
    COMMUNICATION_LOSS_RULE_ID,
    COMMUNICATION_LOSS_RULE_VERSION,
    check_communication_loss,
)
from app.data_quality.rules.sensor_health import (
    SENSOR_DRIFT_RULE_ID,
    SENSOR_DRIFT_RULE_VERSION,
    STUCK_SENSOR_RULE_ID,
    STUCK_SENSOR_RULE_VERSION,
    check_sensor_drift,
    check_stuck_sensor,
)
from app.data_quality.rules.timeliness import (
    CLOCK_STATUS_RULE_ID,
    CLOCK_STATUS_RULE_VERSION,
    STALE_STREAM_RULE_ID,
    STALE_STREAM_RULE_VERSION,
    check_clock_status,
    check_stale_stream,
)
from app.data_quality.services.eligibility import resolve_state
from app.domain.enums import ClockStatus, QualityIssueType, StalenessStatus
from app.domain.models import Telemetry
from app.repositories.telemetry import TelemetryRepository

_SENSOR_WINDOW_RULES = (
    (STALE_STREAM_RULE_ID, STALE_STREAM_RULE_VERSION),
    (CLOCK_STATUS_RULE_ID, CLOCK_STATUS_RULE_VERSION),
    (SENSOR_DRIFT_RULE_ID, SENSOR_DRIFT_RULE_VERSION),
    (STUCK_SENSOR_RULE_ID, STUCK_SENSOR_RULE_VERSION),
)


def _to_point(row: Telemetry) -> TelemetryPoint:
    return TelemetryPoint(
        event_id=row.event_id,
        sensor_id=row.sensor_id,
        source_timestamp=row.source_timestamp,
        persisted_timestamp=row.persisted_timestamp,
        mqtt_received_timestamp=row.mqtt_received_timestamp,
        value=row.value,
        quality=row.quality.value,
        operating_state=row.operating_state,
        measurement_type=row.measurement_type.value,
        sequence_number=row.sequence_number,
    )


class WindowEvaluator:
    def __init__(self, session: AsyncSession, policy: QualityPolicy) -> None:
        self.session = session
        self.policy = policy
        self._telemetry_repo = TelemetryRepository(session)
        self._state_repo = SensorQualityStateRepository(session)
        self._issue_repo = QualityIssueRepository(session)
        self._assessment_repo = QualityAssessmentRepository(session)

    async def evaluate_sensor(
        self,
        tenant_id: uuid.UUID,
        sensor_id: uuid.UUID,
        machine_id: uuid.UUID | None,
        measurement_type: str,
    ) -> None:
        now = datetime.now(UTC)
        context = await self._state_repo.get_context(tenant_id, sensor_id)
        window_minutes = max(
            self.policy.sensor_drift.window_minutes,
            self.policy.stuck_sensor.window_minutes,
            self.policy.clock.drift_window_minutes,
        )
        window_start = now - timedelta(minutes=window_minutes)
        rows = await self._telemetry_repo.get_by_sensor_time_range(
            tenant_id, sensor_id, start=window_start, end=now, limit=2000
        )
        points = [_to_point(row) for row in rows]

        issues: list[RuleIssue] = [
            issue
            for issue in (
                check_stale_stream(context, measurement_type, now, self.policy),
                check_clock_status(points, self.policy),
                check_sensor_drift(points, measurement_type, self.policy),
                check_stuck_sensor(points, measurement_type, self.policy),
            )
            if issue is not None
        ]
        await self._apply_window_issues(
            tenant_id, sensor_id, machine_id, issues, _SENSOR_WINDOW_RULES, window_start, now
        )

        stream_is_stale = any(i.issue_type == QualityIssueType.STALE_STREAM for i in issues)
        if stream_is_stale:
            staleness_status = StalenessStatus.STALE
        elif context.last_observed_at is not None:
            staleness_status = StalenessStatus.FRESH
        else:
            staleness_status = StalenessStatus.UNKNOWN
        clock_status = ClockStatus.NORMAL if points else ClockStatus.UNKNOWN
        for issue in issues:
            if issue.issue_type == QualityIssueType.CLOCK_DRIFT_SUSPECTED:
                clock_status = ClockStatus.DRIFT_SUSPECTED
            elif issue.issue_type == QualityIssueType.CLOCK_OFFSET_SUSPECTED:
                clock_status = ClockStatus.OFFSET_SUSPECTED

        active_severities = await self._issue_repo.list_active_severities(tenant_id, sensor_id)
        quality_state, eligibility = resolve_state(active_severities, self.policy)
        await self._state_repo.upsert(
            tenant_id,
            sensor_id,
            machine_id=machine_id,
            quality_state=quality_state,
            eligibility=eligibility,
            staleness_status=staleness_status,
            clock_status=clock_status,
            active_issue_count=len(active_severities),
            policy_version=self.policy.policy_version,
        )

    async def evaluate_machine_communication(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> None:
        """Machine-wide communication loss (all sensors reporting `COMMUNICATION_LOSS`
        simultaneously — see `communication.py`'s docstring). `QualityIssue.sensor_id` is
        NOT NULL, so the issue is recorded against one deterministically chosen
        *representative* sensor on the machine (lowest sensor_id) — `machine_id` and
        `affected_event_ids`/evidence still cover every sensor involved; API/frontend
        filtering by `machine_id` is the intended way to see this issue, not by sensor."""
        now = datetime.now(UTC)
        window_start = now - timedelta(minutes=5.0)
        rows = await self._telemetry_repo.get_by_machine_time_range(
            tenant_id, machine_id, start=window_start, end=now, limit=2000
        )
        points = [_to_point(row) for row in rows]
        issue = check_communication_loss(machine_id, points, window_start, now)
        issues = [issue] if issue is not None else []

        representative_sensor_id = min({p.sensor_id for p in points}, default=None)
        if representative_sensor_id is None:
            return
        await self._apply_window_issues(
            tenant_id,
            representative_sensor_id,
            machine_id,
            issues,
            ((COMMUNICATION_LOSS_RULE_ID, COMMUNICATION_LOSS_RULE_VERSION),),
            window_start,
            now,
        )

    async def _apply_window_issues(
        self,
        tenant_id: uuid.UUID,
        sensor_id: uuid.UUID,
        machine_id: uuid.UUID | None,
        issues: list[RuleIssue],
        all_rule_keys: tuple[tuple[str, str], ...],
        window_start: datetime,
        window_end: datetime,
    ) -> None:
        fired_rule_ids = {issue.rule_id for issue in issues}
        window_severities = [issue.severity for issue in issues]
        window_state, _ = resolve_state(window_severities, self.policy)
        assessment = await self._assessment_repo.create_window_assessment(
            tenant_id=tenant_id,
            sensor_id=sensor_id,
            machine_id=machine_id,
            window_start=window_start,
            window_end=window_end,
            quality_state=window_state,
            policy_version=self.policy.policy_version,
            rule_versions={issue.rule_id: issue.rule_version for issue in issues},
        )
        for issue in issues:
            await self._issue_repo.upsert_active_window_issue(
                tenant_id=tenant_id,
                sensor_id=sensor_id,
                machine_id=machine_id,
                assessment_id=assessment.id,
                issue=issue,
                policy_version=self.policy.policy_version,
            )
        for rule_id, rule_version in all_rule_keys:
            if rule_id not in fired_rule_ids:
                await self._issue_repo.advance_or_resolve_if_absent(
                    tenant_id=tenant_id,
                    sensor_id=sensor_id,
                    rule_id=rule_id,
                    rule_version=rule_version,
                )
