"""ORDERING dimension — out-of-order arrival and duplicate-delivery *patterns* (Phase 7
brief §10/§11).

Phase 6 already suppresses exact `event_id` duplicates at persistence (idempotent insert).
`check_duplicate_pattern` here is a different, softer signal: the same sensor reporting the
same `source_timestamp` and value under a *different* `event_id` — worth surfacing, never
worth rejecting (brief explicitly warns against flagging legitimately repeated identical
measurements without supporting evidence, which is why this only fires when a genuine
duplicate *candidate* row already exists, not merely because two readings are equal)."""

from __future__ import annotations

from app.data_quality.domain.context import SensorContext
from app.data_quality.domain.results import RuleIssue
from app.domain.enums import IssueSeverity, QualityDimension, QualityIssueType
from app.pipeline.validation import ValidatedTelemetry

OUT_OF_ORDER_RULE_ID = "out_of_order"
OUT_OF_ORDER_RULE_VERSION = "1"

DUPLICATE_PATTERN_RULE_ID = "duplicate_pattern"
DUPLICATE_PATTERN_RULE_VERSION = "1"


def check_out_of_order(event: ValidatedTelemetry, context: SensorContext) -> RuleIssue | None:
    """Never rejects — out-of-order telemetry is fully persistable (Phase 6); this just
    records that arrival order didn't match event-time order."""
    if context.last_source_timestamp_seen is None:
        return None
    if event.source_timestamp >= context.last_source_timestamp_seen:
        return None
    return RuleIssue(
        dimension=QualityDimension.ORDERING,
        issue_type=QualityIssueType.OUT_OF_ORDER,
        severity=IssueSeverity.INFO,
        message=(
            f"event from sensor {event.sensor_id} has source_timestamp "
            f"{event.source_timestamp.isoformat()}, behind the latest already seen "
            f"({context.last_source_timestamp_seen.isoformat()})"
        ),
        rule_id=OUT_OF_ORDER_RULE_ID,
        rule_version=OUT_OF_ORDER_RULE_VERSION,
        evidence={
            "source_timestamp": event.source_timestamp.isoformat(),
            "latest_seen_source_timestamp": context.last_source_timestamp_seen.isoformat(),
        },
        event_id=event.event_id,
    )


def check_duplicate_pattern(
    event: ValidatedTelemetry, duplicate_event_ids: list[str]
) -> RuleIssue | None:
    """`duplicate_event_ids` is pre-fetched by the caller (same sensor_id + source_timestamp
    + value, different event_id, within the policy lookback window) — the query itself
    lives in the repository layer, not here, so this decision stays a pure function."""
    if not duplicate_event_ids:
        return None
    return RuleIssue(
        dimension=QualityDimension.ORDERING,
        issue_type=QualityIssueType.DUPLICATE_PATTERN,
        severity=IssueSeverity.INFO,
        message=(
            f"sensor {event.sensor_id} reported the same value at the same source_timestamp "
            f"under {len(duplicate_event_ids)} other event_id(s)"
        ),
        rule_id=DUPLICATE_PATTERN_RULE_ID,
        rule_version=DUPLICATE_PATTERN_RULE_VERSION,
        evidence={"value": event.value, "source_timestamp": event.source_timestamp.isoformat()},
        affected_event_ids=[str(event.event_id), *duplicate_event_ids],
        event_id=event.event_id,
    )
