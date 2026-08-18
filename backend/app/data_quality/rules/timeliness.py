"""TIMELINESS dimension — late arrival (event-level), staleness and clock offset/drift
(window-level) (Phase 7 brief §12/§13/§14)."""

from __future__ import annotations

from datetime import datetime

from app.data_quality.config.policy import QualityPolicy
from app.data_quality.domain.context import SensorContext, TelemetryPoint
from app.data_quality.domain.results import RuleIssue
from app.domain.enums import IssueSeverity, QualityDimension, QualityIssueType
from app.pipeline.validation import ValidatedTelemetry

LATE_ARRIVAL_RULE_ID = "late_arrival"
LATE_ARRIVAL_RULE_VERSION = "1"

STALE_STREAM_RULE_ID = "stale_stream"
STALE_STREAM_RULE_VERSION = "1"

CLOCK_STATUS_RULE_ID = "clock_status"
CLOCK_STATUS_RULE_VERSION = "1"


def check_late_arrival(
    event: ValidatedTelemetry, mqtt_received_timestamp: datetime, policy: QualityPolicy
) -> RuleIssue | None:
    lateness_seconds = (mqtt_received_timestamp - event.source_timestamp).total_seconds()
    if lateness_seconds < policy.lateness.late_threshold_seconds:
        return None
    very_late = lateness_seconds >= policy.lateness.very_late_threshold_seconds
    return RuleIssue(
        dimension=QualityDimension.TIMELINESS,
        issue_type=(
            QualityIssueType.VERY_LATE_ARRIVAL if very_late else QualityIssueType.LATE_ARRIVAL
        ),
        severity=IssueSeverity.ERROR if very_late else IssueSeverity.WARNING,
        message=(
            f"event from sensor {event.sensor_id} arrived {lateness_seconds:.1f}s after its "
            f"source_timestamp"
        ),
        rule_id=LATE_ARRIVAL_RULE_ID,
        rule_version=LATE_ARRIVAL_RULE_VERSION,
        evidence={
            "lateness_seconds": lateness_seconds,
            "late_threshold_seconds": policy.lateness.late_threshold_seconds,
            "very_late_threshold_seconds": policy.lateness.very_late_threshold_seconds,
        },
        event_id=event.event_id,
    )


def check_stale_stream(
    context: SensorContext, measurement_type: str, now: datetime, policy: QualityPolicy
) -> RuleIssue | None:
    """Window-level, sensor-type-aware (brief §13 — RPM sampled frequently, reservoir
    level less so, must not share one global threshold). Uses only
    `SensorQualityState.last_observed_at`, not a telemetry history query — staleness is
    purely "how long since we last heard from this sensor at all"."""
    if context.last_observed_at is None:
        return None  # never observed yet — nothing to call stale
    expected_interval = policy.expected_interval_seconds_for(measurement_type)
    if expected_interval is None:
        return None
    age_seconds = (now - context.last_observed_at).total_seconds()
    threshold = expected_interval * policy.staleness.stale_multiplier
    if age_seconds < threshold:
        return None
    return RuleIssue(
        dimension=QualityDimension.TIMELINESS,
        issue_type=QualityIssueType.STALE_STREAM,
        severity=IssueSeverity.WARNING,
        message=(
            f"sensor {context.sensor_id} has not reported for {age_seconds:.0f}s "
            f"(expected every ~{expected_interval:.0f}s)"
        ),
        rule_id=STALE_STREAM_RULE_ID,
        rule_version=STALE_STREAM_RULE_VERSION,
        evidence={
            "age_seconds": age_seconds,
            "expected_interval_seconds": expected_interval,
            "stale_multiplier": policy.staleness.stale_multiplier,
        },
        window_start=context.last_observed_at,
        window_end=now,
    )


def check_clock_status(points: list[TelemetryPoint], policy: QualityPolicy) -> RuleIssue | None:
    """Window-level. Distinguishes a constant offset (mean `mqtt_received_timestamp -
    source_timestamp` is non-trivial but stable) from a progressive drift (that gap grows
    over the window) — two separate computations, not one (brief §14). Demo-configuration
    thresholds only; not a claim of real NTP/PTP accuracy."""
    if len(points) < 2:
        return None
    ordered = sorted(points, key=lambda p: p.source_timestamp)
    offsets = [(p.mqtt_received_timestamp - p.source_timestamp).total_seconds() for p in ordered]
    mean_offset = sum(offsets) / len(offsets)

    # Slope of offset over elapsed window time (seconds of offset per minute elapsed) —
    # a simple two-point-endpoint slope is enough to distinguish "flat but offset" from
    # "growing" without a full regression.
    elapsed_minutes = (
        ordered[-1].source_timestamp - ordered[0].source_timestamp
    ).total_seconds() / 60.0
    slope_per_minute = (offsets[-1] - offsets[0]) / elapsed_minutes if elapsed_minutes > 0 else 0.0

    if abs(slope_per_minute) >= policy.clock.drift_slope_warning_seconds_per_minute:
        return RuleIssue(
            dimension=QualityDimension.TIMELINESS,
            issue_type=QualityIssueType.CLOCK_DRIFT_SUSPECTED,
            severity=IssueSeverity.WARNING,
            message=(
                f"clock offset trending by {slope_per_minute:.3f}s/min over the evaluation "
                "window — suggests progressive drift, not a fixed offset"
            ),
            rule_id=CLOCK_STATUS_RULE_ID,
            rule_version=CLOCK_STATUS_RULE_VERSION,
            evidence={
                "mean_offset_seconds": mean_offset,
                "slope_seconds_per_minute": slope_per_minute,
                "sample_count": len(offsets),
            },
            window_start=ordered[0].source_timestamp,
            window_end=ordered[-1].source_timestamp,
        )
    if abs(mean_offset) >= policy.clock.offset_warning_seconds:
        return RuleIssue(
            dimension=QualityDimension.TIMELINESS,
            issue_type=QualityIssueType.CLOCK_OFFSET_SUSPECTED,
            severity=IssueSeverity.INFO,
            message=(
                f"clock offset averaging {mean_offset:.1f}s over the evaluation window, "
                "but stable (not drifting)"
            ),
            rule_id=CLOCK_STATUS_RULE_ID,
            rule_version=CLOCK_STATUS_RULE_VERSION,
            evidence={
                "mean_offset_seconds": mean_offset,
                "slope_seconds_per_minute": slope_per_minute,
                "sample_count": len(offsets),
            },
            window_start=ordered[0].source_timestamp,
            window_end=ordered[-1].source_timestamp,
        )
    return None
