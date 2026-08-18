from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.data_quality.rules.ordering import check_duplicate_pattern, check_out_of_order
from app.domain.enums import QualityIssueType
from tests.data_quality.helpers import make_context, make_event


def test_out_of_order_detected() -> None:
    now = datetime.now(UTC)
    context = make_context(last_source_timestamp_seen=now)
    event = make_event(source_timestamp=now - timedelta(seconds=5))
    issue = check_out_of_order(event, context)
    assert issue is not None
    assert issue.issue_type == QualityIssueType.OUT_OF_ORDER


def test_in_order_raises_nothing() -> None:
    now = datetime.now(UTC)
    context = make_context(last_source_timestamp_seen=now)
    event = make_event(source_timestamp=now + timedelta(seconds=5))
    assert check_out_of_order(event, context) is None


def test_first_event_raises_nothing() -> None:
    context = make_context(last_source_timestamp_seen=None)
    assert check_out_of_order(make_event(), context) is None


def test_duplicate_pattern_detected() -> None:
    event = make_event()
    issue = check_duplicate_pattern(event, [str(event.event_id)])
    assert issue is not None
    assert issue.issue_type == QualityIssueType.DUPLICATE_PATTERN


def test_no_duplicates_raises_nothing() -> None:
    assert check_duplicate_pattern(make_event(), []) is None
