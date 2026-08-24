"""Pure action-readiness derivation — no I/O, no database (Portfolio Intelligence Pass 1
— docs/PORTFOLIO_INTELLIGENCE.md, ADR-177).

Deliberately does not offer "simulation-only auto-eligible" or "blocked by safety/
interlock" states — see `ActionReadinessState`'s own docstring for why: this reference
architecture has no automated-control or interlock subsystem to derive either from, and
introducing them without a real signal would fabricate a capability this platform does
not have (CLAUDE.md "do not fabricate metrics the current domain cannot support").
"""

from __future__ import annotations

from app.domain.enums import ActionReadinessState, ConditionConfidence, ConditionType

#: Condition types that mean "evidence was too weak/ambiguous/quality-limited to reach a
#: reliable condition at all" — distinct from a condition that IS reliably NORMAL_OPERATION.
_BLOCKED_CONDITION_TYPES = frozenset(
    {
        ConditionType.SENSOR_OR_DATA_QUALITY_LIMITATION,
        ConditionType.INSUFFICIENT_EVIDENCE,
        ConditionType.AMBIGUOUS_CONDITION,
    }
)


def derive_action_readiness(
    *,
    has_condition_assessment: bool,
    condition_type: ConditionType | None,
    condition_confidence: ConditionConfidence | None,
    has_open_workflow: bool,
) -> ActionReadinessState:
    """`has_open_workflow` is true when an unresolved `Incident` and/or non-terminal
    `MaintenanceCase` exists for the machine — in this architecture that always implies
    `human_review_required` (there is no auto-approved path), so "manual action
    required" and "human approval required" collapse into one real state,
    `HUMAN_ACTION_REQUIRED`, rather than two the domain cannot actually distinguish."""
    if not has_condition_assessment:
        return ActionReadinessState.NOT_YET_ASSESSED
    if condition_type in _BLOCKED_CONDITION_TYPES:
        return ActionReadinessState.ASSESSMENT_BLOCKED
    if has_open_workflow:
        return ActionReadinessState.HUMAN_ACTION_REQUIRED
    if condition_confidence == ConditionConfidence.LOW:
        return ActionReadinessState.DATA_LIMITED
    return ActionReadinessState.MONITORING_ONLY
