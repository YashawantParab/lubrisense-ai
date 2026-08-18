from __future__ import annotations

from app.data_quality.rules.consistency import check_context_inconsistency
from app.domain.enums import QualityIssueType
from tests.data_quality.helpers import make_event, make_sensor_info


def test_mismatched_measurement_type_detected() -> None:
    sensor_info = make_sensor_info(sensor_type="RPM")
    event = make_event(measurement_type="PRESSURE")
    issue = check_context_inconsistency(event, sensor_info)
    assert issue is not None
    assert issue.issue_type == QualityIssueType.CONTEXT_INCONSISTENCY


def test_matching_measurement_type_raises_nothing() -> None:
    sensor_info = make_sensor_info(sensor_type="PRESSURE")
    event = make_event(measurement_type="PRESSURE")
    assert check_context_inconsistency(event, sensor_info) is None


def test_unknown_sensor_info_raises_nothing() -> None:
    assert check_context_inconsistency(make_event(), None) is None
