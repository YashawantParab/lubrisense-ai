"""VALIDITY dimension — out-of-range, invalid, and unit-mismatched values (Phase 7 brief
§15/§16)."""

from __future__ import annotations

from app.data_quality.config.policy import QualityPolicy
from app.data_quality.domain.context import SensorInfo
from app.data_quality.domain.results import RuleIssue
from app.domain.enums import IssueSeverity, QualityDimension, QualityIssueType
from app.pipeline.validation import ValidatedTelemetry

OUT_OF_RANGE_RULE_ID = "out_of_range"
OUT_OF_RANGE_RULE_VERSION = "1"

INVALID_VALUE_RULE_ID = "invalid_value"
INVALID_VALUE_RULE_VERSION = "1"

UNIT_MISMATCH_RULE_ID = "unit_mismatch"
UNIT_MISMATCH_RULE_VERSION = "1"

_INVALID_QUALITIES = frozenset({"INVALID", "BAD"})


def check_out_of_range(event: ValidatedTelemetry, policy: QualityPolicy) -> RuleIssue | None:
    if event.value is None:
        return None
    value_range = policy.value_range_for(event.measurement_type)
    if value_range is None:
        return None
    low, high = value_range
    if low <= event.value <= high:
        return None
    return RuleIssue(
        dimension=QualityDimension.VALIDITY,
        issue_type=QualityIssueType.OUT_OF_RANGE,
        severity=IssueSeverity.ERROR,
        message=(
            f"{event.measurement_type} value {event.value} outside configured range "
            f"[{low}, {high}] for sensor {event.sensor_id}"
        ),
        rule_id=OUT_OF_RANGE_RULE_ID,
        rule_version=OUT_OF_RANGE_RULE_VERSION,
        evidence={
            "value": event.value,
            "configured_range": [low, high],
            "measurement_type": event.measurement_type,
        },
        event_id=event.event_id,
    )


def check_invalid_value(event: ValidatedTelemetry) -> RuleIssue | None:
    if event.quality not in _INVALID_QUALITIES:
        return None
    return RuleIssue(
        dimension=QualityDimension.VALIDITY,
        issue_type=QualityIssueType.INVALID_VALUE,
        severity=IssueSeverity.ERROR,
        message=f"sensor {event.sensor_id} reported quality={event.quality}",
        rule_id=INVALID_VALUE_RULE_ID,
        rule_version=INVALID_VALUE_RULE_VERSION,
        evidence={"quality": event.quality, "value": event.value},
        event_id=event.event_id,
    )


def check_unit_mismatch(
    event: ValidatedTelemetry, policy: QualityPolicy, sensor_info: SensorInfo | None
) -> RuleIssue | None:
    expected_unit = policy.expected_unit_for(event.measurement_type)
    candidates = {u for u in (expected_unit, sensor_info.unit if sensor_info else None) if u}
    if not candidates or event.unit in candidates:
        return None
    return RuleIssue(
        dimension=QualityDimension.VALIDITY,
        issue_type=QualityIssueType.UNIT_MISMATCH,
        severity=IssueSeverity.WARNING,
        message=(
            f"sensor {event.sensor_id} reported unit {event.unit!r}, expected one of "
            f"{sorted(candidates)!r} for {event.measurement_type}"
        ),
        rule_id=UNIT_MISMATCH_RULE_ID,
        rule_version=UNIT_MISMATCH_RULE_VERSION,
        evidence={"reported_unit": event.unit, "expected_units": sorted(candidates)},
        event_id=event.event_id,
    )
