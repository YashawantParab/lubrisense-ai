from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.data_quality.rules.communication import check_communication_loss
from app.domain.enums import QualityIssueType
from tests.data_quality.helpers import MACHINE_ID, make_point


def test_all_sensors_lost_detected() -> None:
    now = datetime.now(UTC)
    points = [
        make_point(sensor_id=uuid.uuid4(), quality="COMMUNICATION_LOSS"),
        make_point(sensor_id=uuid.uuid4(), quality="COMMUNICATION_LOSS"),
    ]
    issue = check_communication_loss(MACHINE_ID, points, now, now)
    assert issue is not None
    assert issue.issue_type == QualityIssueType.COMMUNICATION_LOSS


def test_partial_loss_is_not_machine_wide() -> None:
    now = datetime.now(UTC)
    points = [
        make_point(sensor_id=uuid.uuid4(), quality="COMMUNICATION_LOSS"),
        make_point(sensor_id=uuid.uuid4(), quality="GOOD"),
    ]
    assert check_communication_loss(MACHINE_ID, points, now, now) is None


def test_single_sensor_machine_never_flagged() -> None:
    """A single-sensor machine's own dropout must never be mistaken for a machine-wide
    network outage — requires at least two reporting sensors."""
    now = datetime.now(UTC)
    points = [make_point(quality="COMMUNICATION_LOSS")]
    assert check_communication_loss(MACHINE_ID, points, now, now) is None


def test_no_points_raises_nothing() -> None:
    now = datetime.now(UTC)
    assert check_communication_loss(MACHINE_ID, [], now, now) is None
