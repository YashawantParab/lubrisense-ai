"""Label-free decision-intelligence contracts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ConditionSnapshot:
    """The minimal slice of a `ConditionAssessment` the `DecisionEngine` needs."""

    id: str
    condition_type: str
    lifecycle_state: str
    severity: str
    confidence: str
    what_is_happening: str


@dataclass(frozen=True, slots=True)
class ProgSnapshot:
    """The minimal slice of one relevant `PrognosticAssessment` the `DecisionEngine`
    needs — the shortest-horizon OK forecast with a threshold crossing, if any."""

    id: str
    status: str
    threshold_crossing_seconds: float | None


@dataclass(frozen=True, slots=True)
class DecisionResult:
    priority: str
    recommended_action: str
    recommended_window: str
    risk_if_deferred: str
    human_review_required: bool
    confidence: str
    evidence: dict[str, object]
    limitations: tuple[str, ...]
    expires_in_seconds: float
