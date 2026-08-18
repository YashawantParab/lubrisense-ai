"""COMMUNICATION dimension — whole-machine communication loss, distinguished from a single
sensor's own dropout (Phase 7 brief §18).

A single sensor reporting `COMMUNICATION_LOSS`/`MISSING` is already captured by
`completeness.check_missing_value` at the event level — that is what a Phase 4
`SENSOR_DROPOUT` scenario produces. This window-level, machine-scoped check looks for the
distinguishing signature of a `NETWORK_FAILURE` scenario instead: *every* sensor on the
machine reporting `COMMUNICATION_LOSS` simultaneously, which no single-sensor check can see
on its own. Requires at least two sensors so a single-sensor machine's own dropout is never
mistaken for a machine-wide outage.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from app.data_quality.domain.context import TelemetryPoint
from app.data_quality.domain.results import RuleIssue
from app.domain.enums import IssueSeverity, QualityDimension, QualityIssueType

COMMUNICATION_LOSS_RULE_ID = "communication_loss"
COMMUNICATION_LOSS_RULE_VERSION = "1"

_MIN_SENSORS_FOR_MACHINE_WIDE_SIGNAL = 2


def check_communication_loss(
    machine_id: uuid.UUID,
    points: list[TelemetryPoint],
    window_start: datetime,
    window_end: datetime,
) -> RuleIssue | None:
    if not points:
        return None
    latest_by_sensor: dict[uuid.UUID, TelemetryPoint] = {}
    for point in points:
        current = latest_by_sensor.get(point.sensor_id)
        if current is None or point.source_timestamp > current.source_timestamp:
            latest_by_sensor[point.sensor_id] = point

    total_sensors = len(latest_by_sensor)
    if total_sensors < _MIN_SENSORS_FOR_MACHINE_WIDE_SIGNAL:
        return None
    affected = [
        str(sid)
        for sid, p in latest_by_sensor.items()
        if p.quality in ("COMMUNICATION_LOSS", "UNAVAILABLE")
    ]
    if len(affected) < total_sensors:
        return None  # partial — individual sensor dropouts, not a machine-wide outage

    return RuleIssue(
        dimension=QualityDimension.COMMUNICATION,
        issue_type=QualityIssueType.COMMUNICATION_LOSS,
        severity=IssueSeverity.ERROR,
        message=(
            f"all {total_sensors} reporting sensors on machine {machine_id} show "
            "communication loss simultaneously — consistent with a gateway/network outage, "
            "not an individual sensor fault"
        ),
        rule_id=COMMUNICATION_LOSS_RULE_ID,
        rule_version=COMMUNICATION_LOSS_RULE_VERSION,
        evidence={"total_sensors": total_sensors, "affected_sensor_ids": affected},
        affected_event_ids=[str(p.event_id) for p in latest_by_sensor.values()],
        window_start=window_start,
        window_end=window_end,
    )
