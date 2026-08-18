from __future__ import annotations

from app.data_quality.rules.completeness import check_missing_value, check_sequence_gap
from app.domain.enums import IssueSeverity, QualityIssueType
from tests.data_quality.helpers import make_context, make_event


def test_missing_value_with_self_labeled_quality_is_warning() -> None:
    event = make_event(value=None, quality="MISSING")
    issue = check_missing_value(event)
    assert issue is not None
    assert issue.issue_type == QualityIssueType.MISSING_VALUE
    assert issue.severity == IssueSeverity.WARNING


def test_missing_value_with_good_quality_is_error() -> None:
    event = make_event(value=None, quality="GOOD")
    issue = check_missing_value(event)
    assert issue is not None
    assert issue.severity == IssueSeverity.ERROR


def test_present_value_raises_nothing() -> None:
    assert check_missing_value(make_event(value=1.0)) is None


def test_sequence_gap_detected() -> None:
    context = make_context(expected_next_sequence=5)
    event = make_event(sequence_number=8)
    issue = check_sequence_gap(event, context)
    assert issue is not None
    assert issue.issue_type == QualityIssueType.SEQUENCE_GAP
    assert issue.evidence["gap_size"] == 3


def test_sequence_gap_not_raised_for_first_event() -> None:
    context = make_context(expected_next_sequence=None)
    assert check_sequence_gap(make_event(sequence_number=100), context) is None


def test_sequence_gap_not_raised_when_in_order() -> None:
    context = make_context(expected_next_sequence=5)
    assert check_sequence_gap(make_event(sequence_number=5), context) is None
