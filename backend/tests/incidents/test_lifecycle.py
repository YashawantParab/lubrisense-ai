"""Pure incident lifecycle transition-validation tests (Phase 16 brief §16.6)."""

from __future__ import annotations

import pytest

from app.domain.enums import IncidentState
from app.incidents.services.lifecycle import InvalidIncidentTransitionError, validate_transition


def test_open_to_acknowledged_is_valid() -> None:
    validate_transition(IncidentState.OPEN, IncidentState.ACKNOWLEDGED)


def test_acknowledged_to_investigating_is_valid() -> None:
    validate_transition(IncidentState.ACKNOWLEDGED, IncidentState.INVESTIGATING)


def test_investigating_to_action_planned_is_valid() -> None:
    validate_transition(IncidentState.INVESTIGATING, IncidentState.ACTION_PLANNED)


def test_action_planned_to_resolved_is_valid() -> None:
    validate_transition(IncidentState.ACTION_PLANNED, IncidentState.RESOLVED)


def test_resolved_to_closed_is_valid() -> None:
    validate_transition(IncidentState.RESOLVED, IncidentState.CLOSED)


def test_resolved_to_reopened_is_valid() -> None:
    validate_transition(IncidentState.RESOLVED, IncidentState.REOPENED)


def test_closed_to_reopened_is_valid() -> None:
    validate_transition(IncidentState.CLOSED, IncidentState.REOPENED)


def test_open_directly_to_closed_is_invalid() -> None:
    """Closing always requires resolution first — never a shortcut skipping the human
    workflow (Phase 16 brief §16.11)."""
    with pytest.raises(InvalidIncidentTransitionError):
        validate_transition(IncidentState.OPEN, IncidentState.CLOSED)


def test_closed_to_open_is_invalid() -> None:
    with pytest.raises(InvalidIncidentTransitionError):
        validate_transition(IncidentState.CLOSED, IncidentState.OPEN)


def test_resolved_to_investigating_is_invalid() -> None:
    with pytest.raises(InvalidIncidentTransitionError):
        validate_transition(IncidentState.RESOLVED, IncidentState.INVESTIGATING)


def test_every_non_terminal_state_can_reach_resolved() -> None:
    for state in (
        IncidentState.DETECTED,
        IncidentState.OPEN,
        IncidentState.ACKNOWLEDGED,
        IncidentState.INVESTIGATING,
        IncidentState.ACTION_PLANNED,
    ):
        validate_transition(state, IncidentState.RESOLVED)
