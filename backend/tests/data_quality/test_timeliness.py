from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.data_quality.rules.timeliness import (
    check_clock_status,
    check_late_arrival,
    check_stale_stream,
)
from app.domain.enums import QualityIssueType
from tests.data_quality.helpers import make_context, make_event, make_point, make_policy


def test_on_time_arrival_raises_nothing() -> None:
    policy = make_policy()
    now = datetime.now(UTC)
    event = make_event(source_timestamp=now)
    assert check_late_arrival(event, now + timedelta(seconds=1), policy) is None


def test_late_arrival_detected() -> None:
    policy = make_policy()
    now = datetime.now(UTC)
    event = make_event(source_timestamp=now)
    issue = check_late_arrival(event, now + timedelta(seconds=45), policy)
    assert issue is not None
    assert issue.issue_type == QualityIssueType.LATE_ARRIVAL


def test_very_late_arrival_detected() -> None:
    policy = make_policy()
    now = datetime.now(UTC)
    event = make_event(source_timestamp=now)
    issue = check_late_arrival(event, now + timedelta(seconds=150), policy)
    assert issue is not None
    assert issue.issue_type == QualityIssueType.VERY_LATE_ARRIVAL


def test_stale_stream_detected() -> None:
    policy = make_policy(
        staleness={"expected_interval_seconds": {"PRESSURE": 10.0}, "stale_multiplier": 3.0}
    )
    now = datetime.now(UTC)
    context = make_context(last_observed_at=now - timedelta(seconds=60))
    issue = check_stale_stream(context, "PRESSURE", now, policy)
    assert issue is not None
    assert issue.issue_type == QualityIssueType.STALE_STREAM


def test_fresh_stream_raises_nothing() -> None:
    policy = make_policy(
        staleness={"expected_interval_seconds": {"PRESSURE": 10.0}, "stale_multiplier": 3.0}
    )
    now = datetime.now(UTC)
    context = make_context(last_observed_at=now - timedelta(seconds=5))
    assert check_stale_stream(context, "PRESSURE", now, policy) is None


def test_never_observed_raises_nothing() -> None:
    policy = make_policy()
    context = make_context(last_observed_at=None)
    assert check_stale_stream(context, "PRESSURE", datetime.now(UTC), policy) is None


def test_clock_drift_detected() -> None:
    policy = make_policy(
        clock={
            "offset_warning_seconds": 5.0,
            "drift_window_minutes": 30.0,
            "drift_slope_warning_seconds_per_minute": 0.05,
        }
    )
    start = datetime.now(UTC)
    points = [
        make_point(source_timestamp=start, mqtt_received_timestamp=start),
        make_point(
            source_timestamp=start + timedelta(minutes=10),
            mqtt_received_timestamp=start + timedelta(minutes=10, seconds=10),
        ),
    ]
    issue = check_clock_status(points, policy)
    assert issue is not None
    assert issue.issue_type == QualityIssueType.CLOCK_DRIFT_SUSPECTED


def test_stable_offset_detected_as_info_not_drift() -> None:
    policy = make_policy(
        clock={
            "offset_warning_seconds": 5.0,
            "drift_window_minutes": 30.0,
            "drift_slope_warning_seconds_per_minute": 0.05,
        }
    )
    start = datetime.now(UTC)
    offset = timedelta(seconds=8)
    points = [
        make_point(source_timestamp=start, mqtt_received_timestamp=start + offset),
        make_point(
            source_timestamp=start + timedelta(minutes=10),
            mqtt_received_timestamp=start + timedelta(minutes=10) + offset,
        ),
    ]
    issue = check_clock_status(points, policy)
    assert issue is not None
    assert issue.issue_type == QualityIssueType.CLOCK_OFFSET_SUSPECTED


def test_normal_clock_raises_nothing() -> None:
    policy = make_policy()
    start = datetime.now(UTC)
    points = [
        make_point(source_timestamp=start, mqtt_received_timestamp=start),
        make_point(
            source_timestamp=start + timedelta(minutes=1),
            mqtt_received_timestamp=start + timedelta(minutes=1),
        ),
    ]
    assert check_clock_status(points, policy) is None
