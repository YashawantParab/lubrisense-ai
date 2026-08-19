"""Pure condition-lifecycle classification (Phase 13 brief §13.11). Compares a new
synthesis result against the machine's recent assessment history (most-recent-first) to
decide `DETECTED`/`DEVELOPING`/`PERSISTENT`/`IMPROVING`/`RESOLVED` — a small, explicit
state machine, not a debounce/hysteresis system like `RuleFindingState` (a condition
assessment is a fresh synthesis judgment every call, not a detector with its own
persistence memory)."""

from __future__ import annotations

from dataclasses import dataclass

from app.condition_intelligence.config.policy import ConditionIntelligencePolicy


@dataclass(frozen=True, slots=True)
class RecentAssessment:
    condition_type: str
    severity: str


@dataclass(frozen=True, slots=True)
class LifecycleResult:
    lifecycle_state: str
    #: True when this assessment continues the same condition_type lineage as the prior
    #: row, so the caller should carry `first_detected_at` forward from that prior row
    #: rather than stamping a fresh "now".
    inherit_first_detected_at: bool


def classify_lifecycle(
    recent: list[RecentAssessment],  # most-recent-first
    new_condition_type: str,
    new_severity: str,
    policy: ConditionIntelligencePolicy,
) -> LifecycleResult:
    if not recent:
        return LifecycleResult("DETECTED", inherit_first_detected_at=False)

    prior = recent[0]

    if new_condition_type == "NORMAL_OPERATION":
        if prior.condition_type != "NORMAL_OPERATION":
            return LifecycleResult("RESOLVED", inherit_first_detected_at=False)
        return LifecycleResult("DETECTED", inherit_first_detected_at=False)

    if prior.condition_type != new_condition_type:
        return LifecycleResult("DETECTED", inherit_first_detected_at=False)

    # Same condition_type as the immediately preceding assessment — count the run of
    # consecutive same-type rows (including this new one) to decide DEVELOPING vs.
    # PERSISTENT.
    consecutive = 1
    for row in recent:
        if row.condition_type == new_condition_type:
            consecutive += 1
        else:
            break

    if policy.rank(new_severity) < policy.rank(prior.severity):
        return LifecycleResult("IMPROVING", inherit_first_detected_at=True)
    if consecutive >= policy.lifecycle.persistent_after_consecutive:
        return LifecycleResult("PERSISTENT", inherit_first_detected_at=True)
    if consecutive >= policy.lifecycle.developing_after_consecutive:
        return LifecycleResult("DEVELOPING", inherit_first_detected_at=True)
    return LifecycleResult("DETECTED", inherit_first_detected_at=True)
