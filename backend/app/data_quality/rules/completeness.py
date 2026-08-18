"""COMPLETENESS dimension — missing values and sequence gaps (Phase 7 brief §8/§9).

Never zero-substitutes a missing observation: `MISSING_VALUE` is raised whenever
`value is None`, regardless of the reason, and the original `quality` label from Phase 5/6
(`MISSING`/`UNAVAILABLE`/etc.) is preserved verbatim in the issue's evidence, not erased.
"""

from __future__ import annotations

from app.data_quality.domain.context import SensorContext
from app.data_quality.domain.results import RuleIssue
from app.domain.enums import IssueSeverity, QualityDimension, QualityIssueType
from app.pipeline.validation import ValidatedTelemetry

MISSING_VALUE_RULE_ID = "missing_value"
MISSING_VALUE_RULE_VERSION = "1"

SEQUENCE_GAP_RULE_ID = "sequence_gap"
SEQUENCE_GAP_RULE_VERSION = "1"

# Qualities that already explain *why* the value is missing — a genuinely absent
# observation, not a value/quality inconsistency.
_EXPECTED_MISSING_QUALITIES = frozenset({"MISSING", "UNAVAILABLE", "COMMUNICATION_LOSS"})


def check_missing_value(event: ValidatedTelemetry) -> RuleIssue | None:
    if event.value is not None:
        return None
    expected = event.quality in _EXPECTED_MISSING_QUALITIES
    return RuleIssue(
        dimension=QualityDimension.COMPLETENESS,
        issue_type=QualityIssueType.MISSING_VALUE,
        # A self-labeled gap (edge already said MISSING/UNAVAILABLE/COMMUNICATION_LOSS) is
        # expected and only WARNING; a GOOD-quality event with no value is a real
        # value/quality inconsistency and worth ERROR.
        severity=IssueSeverity.WARNING if expected else IssueSeverity.ERROR,
        message=(
            f"sensor {event.sensor_id} reported no value for {event.measurement_type} "
            f"(quality={event.quality})"
        ),
        rule_id=MISSING_VALUE_RULE_ID,
        rule_version=MISSING_VALUE_RULE_VERSION,
        evidence={"quality": event.quality, "measurement_type": event.measurement_type},
        event_id=event.event_id,
    )


def check_sequence_gap(event: ValidatedTelemetry, context: SensorContext) -> RuleIssue | None:
    """Uses the Phase 5 persisted per-(gateway, sensor) sequence number. Only fires on a
    forward jump (a gap); a sequence number arriving *behind* what's already been seen is
    an ordering/duplicate concern, not a gap (see `ordering.py`)."""
    if context.expected_next_sequence is None:
        return None  # first event seen for this sensor — nothing to compare against yet
    if event.sequence_number <= context.expected_next_sequence:
        return None
    gap_size = event.sequence_number - context.expected_next_sequence
    return RuleIssue(
        dimension=QualityDimension.COMPLETENESS,
        issue_type=QualityIssueType.SEQUENCE_GAP,
        severity=IssueSeverity.WARNING,
        message=(
            f"sequence gap for sensor {event.sensor_id}: expected "
            f"{context.expected_next_sequence}, observed {event.sequence_number} "
            f"({gap_size} missing)"
        ),
        rule_id=SEQUENCE_GAP_RULE_ID,
        rule_version=SEQUENCE_GAP_RULE_VERSION,
        evidence={
            "expected_sequence": context.expected_next_sequence,
            "observed_sequence": event.sequence_number,
            "gap_size": gap_size,
        },
        event_id=event.event_id,
    )
