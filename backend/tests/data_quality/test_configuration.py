from __future__ import annotations

from app.data_quality.rules.configuration import check_config_change
from app.domain.enums import IssueSeverity, QualityIssueType
from tests.data_quality.helpers import make_context, make_event


def test_firmware_change_detected_as_info() -> None:
    context = make_context(firmware_version="1.0.0")
    event = make_event(firmware_version="1.1.0")
    issue = check_config_change(event, context)
    assert issue is not None
    assert issue.issue_type == QualityIssueType.CONFIG_CHANGE
    assert issue.severity == IssueSeverity.INFO


def test_unchanged_firmware_raises_nothing() -> None:
    context = make_context(firmware_version="1.0.0")
    event = make_event(firmware_version="1.0.0")
    assert check_config_change(event, context) is None


def test_first_observation_raises_nothing() -> None:
    context = make_context(firmware_version=None)
    event = make_event(firmware_version="1.0.0")
    assert check_config_change(event, context) is None
