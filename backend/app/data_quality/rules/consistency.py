"""CONTEXT/CONSISTENCY dimensions — schema/metadata inconsistencies that are valid-but-
suspicious, as distinct from Phase 6's structural rejection (Phase 7 brief §17).

Phase 6 already rejects events referencing an unknown sensor. This module checks something
subtler Phase 6 never looks at: a sensor that *does* exist but is reporting a
`measurement_type` that doesn't match how it's actually configured in the asset hierarchy —
plausible causes include a firmware misconfiguration or a wiring swap, not something a
structural/tenant check would ever catch.
"""

from __future__ import annotations

from app.data_quality.domain.context import SensorInfo
from app.data_quality.domain.results import RuleIssue
from app.domain.enums import IssueSeverity, QualityDimension, QualityIssueType
from app.pipeline.validation import ValidatedTelemetry

CONTEXT_INCONSISTENCY_RULE_ID = "context_inconsistency"
CONTEXT_INCONSISTENCY_RULE_VERSION = "1"


def check_context_inconsistency(
    event: ValidatedTelemetry, sensor_info: SensorInfo | None
) -> RuleIssue | None:
    if sensor_info is None or event.measurement_type == sensor_info.sensor_type:
        return None
    return RuleIssue(
        dimension=QualityDimension.CONTEXT,
        issue_type=QualityIssueType.CONTEXT_INCONSISTENCY,
        severity=IssueSeverity.ERROR,
        message=(
            f"sensor {event.sensor_id} is configured as {sensor_info.sensor_type} but "
            f"reported measurement_type {event.measurement_type}"
        ),
        rule_id=CONTEXT_INCONSISTENCY_RULE_ID,
        rule_version=CONTEXT_INCONSISTENCY_RULE_VERSION,
        evidence={
            "configured_sensor_type": sensor_info.sensor_type,
            "reported_measurement_type": event.measurement_type,
        },
        event_id=event.event_id,
    )
