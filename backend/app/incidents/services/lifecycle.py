"""Pure incident lifecycle transition validation (Phase 16 brief §16.6: "Use explicit
state transition validation")."""

from __future__ import annotations

from app.domain.enums import IncidentState

_VALID_TRANSITIONS: dict[IncidentState, frozenset[IncidentState]] = {
    IncidentState.DETECTED: frozenset(
        {IncidentState.OPEN, IncidentState.ACKNOWLEDGED, IncidentState.RESOLVED}
    ),
    IncidentState.OPEN: frozenset({IncidentState.ACKNOWLEDGED, IncidentState.RESOLVED}),
    IncidentState.ACKNOWLEDGED: frozenset({IncidentState.INVESTIGATING, IncidentState.RESOLVED}),
    IncidentState.INVESTIGATING: frozenset({IncidentState.ACTION_PLANNED, IncidentState.RESOLVED}),
    IncidentState.ACTION_PLANNED: frozenset({IncidentState.RESOLVED}),
    IncidentState.RESOLVED: frozenset({IncidentState.CLOSED, IncidentState.REOPENED}),
    IncidentState.CLOSED: frozenset({IncidentState.REOPENED}),
    IncidentState.REOPENED: frozenset({IncidentState.ACKNOWLEDGED, IncidentState.INVESTIGATING}),
}


class InvalidIncidentTransitionError(ValueError):
    def __init__(self, current: IncidentState, target: IncidentState) -> None:
        super().__init__(f"Cannot transition incident from {current.value} to {target.value}.")
        self.current = current
        self.target = target


def validate_transition(current: IncidentState, target: IncidentState) -> None:
    if target not in _VALID_TRANSITIONS.get(current, frozenset()):
        raise InvalidIncidentTransitionError(current, target)
