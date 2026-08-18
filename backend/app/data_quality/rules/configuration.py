"""CONFIGURATION dimension — firmware/config-version-change awareness (Phase 7 brief §22).

A version change is recorded as a marker, deliberately never itself treated as a fault —
it matters because baseline behavior may shift afterward, which is exactly the kind of
context later phases (baselines, Phase 8) need, not evidence of a problem today.
"""

from __future__ import annotations

from app.data_quality.domain.context import SensorContext
from app.data_quality.domain.results import RuleIssue
from app.domain.enums import IssueSeverity, QualityDimension, QualityIssueType
from app.pipeline.validation import ValidatedTelemetry

CONFIG_CHANGE_RULE_ID = "config_change"
CONFIG_CHANGE_RULE_VERSION = "1"


def check_config_change(event: ValidatedTelemetry, context: SensorContext) -> RuleIssue | None:
    firmware_changed = (
        context.firmware_version is not None
        and event.firmware_version is not None
        and event.firmware_version != context.firmware_version
    )
    controller_changed = (
        context.controller_version is not None
        and event.controller_version is not None
        and event.controller_version != context.controller_version
    )
    if not firmware_changed and not controller_changed:
        return None
    return RuleIssue(
        dimension=QualityDimension.CONFIGURATION,
        issue_type=QualityIssueType.CONFIG_CHANGE,
        severity=IssueSeverity.INFO,
        message=(
            f"sensor {event.sensor_id} configuration changed — firmware "
            f"{context.firmware_version!r} -> {event.firmware_version!r}, controller "
            f"{context.controller_version!r} -> {event.controller_version!r}"
        ),
        rule_id=CONFIG_CHANGE_RULE_ID,
        rule_version=CONFIG_CHANGE_RULE_VERSION,
        evidence={
            "previous_firmware_version": context.firmware_version,
            "new_firmware_version": event.firmware_version,
            "previous_controller_version": context.controller_version,
            "new_controller_version": event.controller_version,
        },
        event_id=event.event_id,
    )
