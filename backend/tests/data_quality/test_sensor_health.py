from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.data_quality.config.policy import QualityPolicy
from app.data_quality.rules.sensor_health import (
    check_sensor_drift,
    check_spike,
    check_stuck_sensor,
)
from app.domain.enums import QualityIssueType
from tests.data_quality.helpers import make_context, make_event, make_point, make_policy


def _drift_policy() -> QualityPolicy:
    return make_policy(
        sensor_drift={
            "window_minutes": 180.0,
            "min_samples": 4,
            "bias_fraction_of_range_warning": 0.05,
            "bias_fraction_of_range_error": 0.5,
        }
    )


def test_sensor_drift_detected() -> None:
    policy = _drift_policy()
    start = datetime.now(UTC)
    points = [
        make_point(source_timestamp=start, value=5.0),
        make_point(source_timestamp=start + timedelta(minutes=1), value=5.1),
        make_point(source_timestamp=start + timedelta(minutes=2), value=10.0),
        make_point(source_timestamp=start + timedelta(minutes=3), value=10.1),
    ]
    issue = check_sensor_drift(points, "PRESSURE", policy)
    assert issue is not None
    assert issue.issue_type == QualityIssueType.SENSOR_DRIFT_SUSPECTED


def test_stable_signal_raises_nothing() -> None:
    policy = _drift_policy()
    start = datetime.now(UTC)
    points = [
        make_point(source_timestamp=start + timedelta(minutes=i), value=5.0 + (i % 2) * 0.01)
        for i in range(4)
    ]
    assert check_sensor_drift(points, "PRESSURE", policy) is None


def test_drift_skipped_below_min_samples() -> None:
    policy = _drift_policy()
    points = [make_point(value=5.0), make_point(value=10.0)]
    assert check_sensor_drift(points, "PRESSURE", policy) is None


def _stuck_policy() -> QualityPolicy:
    return make_policy(
        stuck_sensor={"window_minutes": 20.0, "min_samples": 3, "tolerant_types": []}
    )


def test_stuck_sensor_detected() -> None:
    policy = _stuck_policy()
    points = [make_point(value=5.0) for _ in range(4)]
    issue = check_stuck_sensor(points, "PRESSURE", policy)
    assert issue is not None
    assert issue.issue_type == QualityIssueType.STUCK_SENSOR_SUSPECTED


def test_varying_values_raise_nothing() -> None:
    policy = _stuck_policy()
    points = [make_point(value=float(i)) for i in range(4)]
    assert check_stuck_sensor(points, "PRESSURE", policy) is None


def test_tolerant_type_never_flagged() -> None:
    policy = make_policy(
        stuck_sensor={
            "window_minutes": 20.0,
            "min_samples": 3,
            "tolerant_types": ["CYCLE_COMPLETION"],
        }
    )
    points = [make_point(value=1.0, measurement_type="CYCLE_COMPLETION") for _ in range(4)]
    assert check_stuck_sensor(points, "CYCLE_COMPLETION", policy) is None


def test_stopped_activity_signal_never_flagged() -> None:
    """RPM=0 while STOPPED is legitimate, not a stuck sensor (brief §20/§25)."""
    policy = _stuck_policy()
    points = [make_point(value=0.0, operating_state="STOPPED") for _ in range(4)]
    assert check_stuck_sensor(points, "RPM", policy) is None


def _spike_policy() -> QualityPolicy:
    return make_policy(
        validity={
            "value_ranges": {"PRESSURE": (0.0, 25.0)},
            "expected_unit": {"PRESSURE": "bar"},
        },
        spike={"rate_of_change_fraction_of_range": {"PRESSURE": 0.1}},
    )


def test_spike_detected() -> None:
    policy = _spike_policy()
    context = make_context(
        last_observed_value=5.0, last_observed_operating_state="RUNNING_NORMAL_LOAD"
    )
    event = make_event(value=20.0, operating_state="RUNNING_NORMAL_LOAD")
    issue = check_spike(event, context, policy)
    assert issue is not None
    assert issue.issue_type == QualityIssueType.SPIKE_DETECTED


def test_small_change_raises_nothing() -> None:
    policy = _spike_policy()
    context = make_context(
        last_observed_value=5.0, last_observed_operating_state="RUNNING_NORMAL_LOAD"
    )
    event = make_event(value=5.5, operating_state="RUNNING_NORMAL_LOAD")
    assert check_spike(event, context, policy) is None


def test_spike_skipped_on_operating_state_transition() -> None:
    """A legitimate state transition (e.g. STARTING -> RUNNING) explains a large jump —
    never flagged as a spike (brief §25)."""
    policy = _spike_policy()
    context = make_context(last_observed_value=0.0, last_observed_operating_state="STOPPED")
    event = make_event(value=20.0, operating_state="RUNNING_NORMAL_LOAD")
    assert check_spike(event, context, policy) is None
