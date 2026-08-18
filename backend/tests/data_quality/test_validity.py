from __future__ import annotations

from app.data_quality.rules.validity import (
    check_invalid_value,
    check_out_of_range,
    check_unit_mismatch,
)
from app.domain.enums import QualityIssueType
from tests.data_quality.helpers import make_event, make_policy, make_sensor_info


def test_out_of_range_detected() -> None:
    policy = make_policy()
    event = make_event(measurement_type="PRESSURE", value=99.0)
    issue = check_out_of_range(event, policy)
    assert issue is not None
    assert issue.issue_type == QualityIssueType.OUT_OF_RANGE


def test_in_range_raises_nothing() -> None:
    policy = make_policy()
    assert check_out_of_range(make_event(measurement_type="PRESSURE", value=10.0), policy) is None


def test_out_of_range_skipped_when_no_configured_range() -> None:
    policy = make_policy()
    assert check_out_of_range(make_event(measurement_type="LOAD", value=99999.0), policy) is None


def test_out_of_range_skipped_for_missing_value() -> None:
    policy = make_policy()
    assert check_out_of_range(make_event(value=None), policy) is None


def test_invalid_quality_detected() -> None:
    issue = check_invalid_value(make_event(quality="INVALID"))
    assert issue is not None
    assert issue.issue_type == QualityIssueType.INVALID_VALUE


def test_good_quality_raises_nothing() -> None:
    assert check_invalid_value(make_event(quality="GOOD")) is None


def test_unit_mismatch_detected() -> None:
    policy = make_policy()
    sensor_info = make_sensor_info(sensor_type="PRESSURE", unit="bar")
    event = make_event(measurement_type="PRESSURE", unit="psi")
    issue = check_unit_mismatch(event, policy, sensor_info)
    assert issue is not None
    assert issue.issue_type == QualityIssueType.UNIT_MISMATCH


def test_unit_matching_expected_raises_nothing() -> None:
    policy = make_policy()
    sensor_info = make_sensor_info(sensor_type="PRESSURE", unit="bar")
    event = make_event(measurement_type="PRESSURE", unit="bar")
    assert check_unit_mismatch(event, policy, sensor_info) is None


def test_unit_matching_sensor_configured_unit_raises_nothing() -> None:
    """A sensor's own configured unit is an acceptable candidate too, even if it differs
    from the policy's expected unit for the reported measurement_type."""
    policy = make_policy()
    sensor_info = make_sensor_info(sensor_type="PRESSURE", unit="kPa")
    event = make_event(measurement_type="PRESSURE", unit="kPa")
    assert check_unit_mismatch(event, policy, sensor_info) is None
