"""Event-level orchestration (Phase 7 brief §6 — the synchronous-per-event half of the
event/window split; plan decision #5).

Runs every event-scoped rule for one already-validated-and-enriched telemetry event, using
only the current event plus the small cached `SensorContext` on `SensorQualityState` — never
a fresh time-range query (that's `WindowEvaluator`'s job). Persists a `QualityAssessment` +
`QualityIssue` row(s) only when at least one issue was actually found (storage strategy,
plan decision #4); always upserts the always-current `SensorQualityState` row.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.data_quality.config.policy import QualityPolicy
from app.data_quality.domain.context import SensorInfo
from app.data_quality.domain.results import RuleIssue
from app.data_quality.repositories.quality_assessment_repository import (
    QualityAssessmentRepository,
)
from app.data_quality.repositories.quality_issue_repository import QualityIssueRepository
from app.data_quality.repositories.sensor_quality_state_repository import (
    SensorQualityStateRepository,
)
from app.data_quality.rules.completeness import check_missing_value, check_sequence_gap
from app.data_quality.rules.configuration import check_config_change
from app.data_quality.rules.consistency import check_context_inconsistency
from app.data_quality.rules.ordering import check_duplicate_pattern, check_out_of_order
from app.data_quality.rules.sensor_health import check_spike
from app.data_quality.rules.timeliness import check_late_arrival
from app.data_quality.rules.validity import (
    check_invalid_value,
    check_out_of_range,
    check_unit_mismatch,
)
from app.data_quality.services.eligibility import resolve_state, worst_severity
from app.domain.enums import IssueSeverity
from app.domain.models import Sensor
from app.pipeline.enrichment import EnrichedContext
from app.pipeline.validation import ValidatedTelemetry
from app.repositories.telemetry import TelemetryRepository


class QualityEngine:
    def __init__(self, session: AsyncSession, policy: QualityPolicy) -> None:
        self.session = session
        self.policy = policy
        self._state_repo = SensorQualityStateRepository(session)
        self._issue_repo = QualityIssueRepository(session)
        self._assessment_repo = QualityAssessmentRepository(session)
        self._telemetry_repo = TelemetryRepository(session)

    async def process_event(
        self,
        event: ValidatedTelemetry,
        enriched: EnrichedContext,
        sensor: Sensor,
        mqtt_received_timestamp: datetime,
    ) -> None:
        context = await self._state_repo.get_context(event.tenant_id, event.sensor_id)
        sensor_info = SensorInfo(sensor_type=sensor.sensor_type.value, unit=sensor.unit)

        issues: list[RuleIssue] = [
            issue
            for issue in (
                check_missing_value(event),
                check_sequence_gap(event, context),
                check_out_of_range(event, self.policy),
                check_invalid_value(event),
                check_unit_mismatch(event, self.policy, sensor_info),
                check_late_arrival(event, mqtt_received_timestamp, self.policy),
                check_out_of_order(event, context),
                check_context_inconsistency(event, sensor_info),
                check_spike(event, context, self.policy),
                check_config_change(event, context),
            )
            if issue is not None
        ]

        duplicate_ids = await self._telemetry_repo.find_duplicate_candidates(
            event.tenant_id,
            event.sensor_id,
            source_timestamp=event.source_timestamp,
            value=event.value,
            exclude_event_id=event.event_id,
            lookback_start=event.source_timestamp
            - timedelta(minutes=self.policy.duplicate_pattern.lookback_minutes),
        )
        duplicate_issue = check_duplicate_pattern(event, [str(d) for d in duplicate_ids])
        if duplicate_issue is not None:
            issues.append(duplicate_issue)

        event_severities = [issue.severity for issue in issues]

        if issues:
            event_state, _event_eligibility = resolve_state(event_severities, self.policy)
            rule_versions = {issue.rule_id: issue.rule_version for issue in issues}
            assessment = await self._assessment_repo.create_event_assessment(
                tenant_id=event.tenant_id,
                sensor_id=event.sensor_id,
                machine_id=enriched.machine_id,
                event_id=event.event_id,
                quality_state=event_state,
                policy_version=self.policy.policy_version,
                rule_versions=rule_versions,
            )
            for issue in issues:
                await self._issue_repo.create_event_issue(
                    tenant_id=event.tenant_id,
                    sensor_id=event.sensor_id,
                    machine_id=enriched.machine_id,
                    assessment_id=assessment.id,
                    issue=issue,
                    policy_version=self.policy.policy_version,
                )

        active_window_severities = await self._issue_repo.list_active_severities(
            event.tenant_id, event.sensor_id
        )
        quality_state, eligibility = resolve_state(
            event_severities + active_window_severities, self.policy
        )
        active_issue_count = len(active_window_severities)

        is_latest = (
            context.last_source_timestamp_seen is None
            or event.source_timestamp >= context.last_source_timestamp_seen
        )
        is_good_reading = event.value is not None and worst_severity(event_severities) not in (
            IssueSeverity.ERROR,
            IssueSeverity.CRITICAL,
        )

        update_fields: dict[str, object] = {
            "machine_id": enriched.machine_id,
            "quality_state": quality_state,
            "eligibility": eligibility,
            "active_issue_count": active_issue_count,
            "policy_version": self.policy.policy_version,
        }
        if is_latest:
            update_fields.update(
                last_observed_at=event.source_timestamp,
                last_observed_event_id=event.event_id,
                last_observed_value=event.value,
                last_observed_quality=event.quality,
                last_observed_operating_state=event.operating_state,
                last_source_timestamp_seen=event.source_timestamp,
            )
            if context.expected_next_sequence is None or (
                event.sequence_number >= context.expected_next_sequence
            ):
                update_fields["expected_next_sequence"] = event.sequence_number + 1
            if event.firmware_version is not None:
                update_fields["firmware_version"] = event.firmware_version
            if event.controller_version is not None:
                update_fields["controller_version"] = event.controller_version
            if is_good_reading:
                update_fields["last_good_reading_at"] = event.source_timestamp
                update_fields["last_good_reading_value"] = event.value

        await self._state_repo.upsert(event.tenant_id, event.sensor_id, **update_fields)
