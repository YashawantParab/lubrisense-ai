"""SENSOR_HEALTH dimension — drift, stuck-value, and spike/rate-of-change suspicion (Phase
7 brief §19/§20/§21). None of these are ML and none of them declare a fault outright —
language stays "SUSPECTED", matching `docs/FAILURE_MODE_CATALOG.md`'s calibrated-evidence
convention (never asserted direct causality from simple correlation).
"""

from __future__ import annotations

from app.data_quality.config.policy import QualityPolicy
from app.data_quality.domain.context import SensorContext, TelemetryPoint
from app.data_quality.domain.results import RuleIssue
from app.domain.enums import IssueSeverity, QualityDimension, QualityIssueType
from app.pipeline.validation import ValidatedTelemetry

SENSOR_DRIFT_RULE_ID = "sensor_drift_suspected"
SENSOR_DRIFT_RULE_VERSION = "1"

STUCK_SENSOR_RULE_ID = "stuck_sensor_suspected"
STUCK_SENSOR_RULE_VERSION = "1"

SPIKE_RULE_ID = "spike_detected"
SPIKE_RULE_VERSION = "1"

# A run of values this close together (absolute) is treated as bit-identical for the stuck
# check — every synthetic sensor's own noise_std is >= 0.01 in demo_engineering.yaml, so
# real variation is always far larger than this.
_STUCK_EPSILON = 1e-6

# Measurement types where a machine being STOPPED plausibly explains a flat reading on its
# own — checked before ever raising STUCK_SENSOR_SUSPECTED (brief §20/§25).
_ACTIVITY_CORRELATED_TYPES = frozenset(
    {"RPM", "LOAD", "PUMP_CURRENT", "VIBRATION_RMS", "VIBRATION_PEAK", "FLOW", "PRESSURE"}
)


def check_sensor_drift(
    points: list[TelemetryPoint], measurement_type: str, policy: QualityPolicy
) -> RuleIssue | None:
    """Mean-shift over the window (first half vs. second half) — deliberately simpler than
    a full linear regression, and just as sufficient to catch the Phase 4 SENSOR_DRIFT
    scenario's monotonic bias growth, which stays GOOD-quality the whole time (this is the
    *only* way to notice it — nothing in `quality` flags it)."""
    value_range = policy.value_range_for(measurement_type)
    if value_range is None:
        return None
    usable = [p for p in points if p.value is not None]
    if len(usable) < policy.sensor_drift.min_samples:
        return None
    ordered = sorted(usable, key=lambda p: p.source_timestamp)
    midpoint = len(ordered) // 2
    first_half = ordered[:midpoint]
    second_half = ordered[midpoint:]
    if not first_half or not second_half:
        return None

    first_mean = sum(p.value for p in first_half if p.value is not None) / len(first_half)
    second_mean = sum(p.value for p in second_half if p.value is not None) / len(second_half)
    low, high = value_range
    span = high - low
    if span <= 0:
        return None
    shift_fraction = abs(second_mean - first_mean) / span

    if shift_fraction < policy.sensor_drift.bias_fraction_of_range_warning:
        return None
    severity = (
        IssueSeverity.WARNING
        if shift_fraction < policy.sensor_drift.bias_fraction_of_range_error
        else IssueSeverity.ERROR
    )
    return RuleIssue(
        dimension=QualityDimension.SENSOR_HEALTH,
        issue_type=QualityIssueType.SENSOR_DRIFT_SUSPECTED,
        severity=severity,
        message=(
            f"signal is consistent with gradual sensor drift for {measurement_type} — mean "
            f"shifted {shift_fraction * 100:.1f}% of the valid range across the evaluation "
            "window; confidence in downstream condition assessments for this signal is "
            "reduced accordingly"
        ),
        rule_id=SENSOR_DRIFT_RULE_ID,
        rule_version=SENSOR_DRIFT_RULE_VERSION,
        evidence={
            "first_half_mean": first_mean,
            "second_half_mean": second_mean,
            "shift_fraction_of_range": shift_fraction,
            "sample_count": len(usable),
        },
        affected_event_ids=[str(p.event_id) for p in ordered],
        window_start=ordered[0].source_timestamp,
        window_end=ordered[-1].source_timestamp,
    )


def check_stuck_sensor(
    points: list[TelemetryPoint], measurement_type: str, policy: QualityPolicy
) -> RuleIssue | None:
    if measurement_type in policy.stuck_sensor.tolerant_types:
        return None
    usable = [p for p in points if p.value is not None]
    if len(usable) < policy.stuck_sensor.min_samples:
        return None
    values = [p.value for p in usable if p.value is not None]
    if (max(values) - min(values)) >= _STUCK_EPSILON:
        return None
    # Constant value — but a STOPPED machine legitimately explains a flat activity-
    # correlated signal (brief §25: RPM=0 while STOPPED is not poor quality).
    if measurement_type in _ACTIVITY_CORRELATED_TYPES and all(
        p.operating_state == "STOPPED" for p in usable
    ):
        return None
    ordered = sorted(usable, key=lambda p: p.source_timestamp)
    return RuleIssue(
        dimension=QualityDimension.SENSOR_HEALTH,
        issue_type=QualityIssueType.STUCK_SENSOR_SUSPECTED,
        severity=IssueSeverity.WARNING,
        message=(
            f"{measurement_type} has reported the same value ({values[0]}) for "
            f"{len(usable)} consecutive readings — suspected stuck sensor"
        ),
        rule_id=STUCK_SENSOR_RULE_ID,
        rule_version=STUCK_SENSOR_RULE_VERSION,
        evidence={"constant_value": values[0], "sample_count": len(usable)},
        affected_event_ids=[str(p.event_id) for p in ordered],
        window_start=ordered[0].source_timestamp,
        window_end=ordered[-1].source_timestamp,
    )


def check_spike(
    event: ValidatedTelemetry, context: SensorContext, policy: QualityPolicy
) -> RuleIssue | None:
    """Only applies the rate-of-change limit when `operating_state` is unchanged since the
    last observation — a state transition (e.g. STARTING -> RUNNING) is exactly when a
    large, legitimate jump happens (brief §25)."""
    if event.value is None or context.last_observed_value is None:
        return None
    if context.last_observed_operating_state != event.operating_state:
        return None
    limit = policy.rate_of_change_limit_for(event.measurement_type)
    if limit is None:
        return None
    delta = abs(event.value - context.last_observed_value)
    if delta <= limit:
        return None
    return RuleIssue(
        dimension=QualityDimension.SENSOR_HEALTH,
        issue_type=QualityIssueType.SPIKE_DETECTED,
        severity=IssueSeverity.WARNING,
        message=(
            f"{event.measurement_type} changed by {delta} in one reading for sensor "
            f"{event.sensor_id} (limit {limit}), operating_state unchanged "
            f"({event.operating_state})"
        ),
        rule_id=SPIKE_RULE_ID,
        rule_version=SPIKE_RULE_VERSION,
        evidence={
            "previous_value": context.last_observed_value,
            "new_value": event.value,
            "delta": delta,
            "limit": limit,
        },
        event_id=event.event_id,
    )
