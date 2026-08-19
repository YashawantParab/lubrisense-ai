"""Pure decision-synthesis logic (Phase 14 brief) — no I/O, no database. Priority is an
explicit, explainable tier computation (severity -> base tier, then bounded +1 adjustments
for persistence/criticality/imminent forecasted crossing), never an opaque weighted sum
(Phase 14 brief §14.4/§14.10)."""

from __future__ import annotations

from app.decision_intelligence.config.policy import DecisionIntelligencePolicy
from app.decision_intelligence.domain.models import ConditionSnapshot, DecisionResult, ProgSnapshot

#: Condition types that never reach the fault-pattern priority/action path, regardless of
#: severity — each has its own fixed, cautious handling instead (Phase 14 brief §14.9).
_NON_FAULT_TYPES = frozenset(
    {
        "NORMAL_OPERATION",
        "INSUFFICIENT_EVIDENCE",
        "SENSOR_OR_DATA_QUALITY_LIMITATION",
        "AMBIGUOUS_CONDITION",
    }
)


def decide(
    condition: ConditionSnapshot,
    prognostics: list[ProgSnapshot],
    criticality: str,
    policy: DecisionIntelligencePolicy,
) -> DecisionResult:
    action = policy.condition_action_map[condition.condition_type]
    limitations: list[str] = []

    if condition.condition_type in _NON_FAULT_TYPES:
        priority = "MONITOR" if condition.condition_type == "NORMAL_OPERATION" else "PLANNED"
        if condition.condition_type in (
            "INSUFFICIENT_EVIDENCE",
            "SENSOR_OR_DATA_QUALITY_LIMITATION",
        ):
            limitations.append(
                "Evidence quality is limited; a maintenance action is not recommended until "
                "verified."
            )
        if condition.condition_type == "AMBIGUOUS_CONDITION":
            limitations.append("Evidence disagrees on root cause; recommendation is conservative.")
    else:
        tier = policy.severity_priority_tier[condition.severity]
        adjustments: list[str] = []

        if condition.lifecycle_state == "PERSISTENT":
            tier += policy.tier_adjustments.persistent_lifecycle
            adjustments.append("persistent lifecycle")

        if criticality in ("HIGH", "CRITICAL"):
            tier += policy.tier_adjustments.criticality_high_or_critical
            adjustments.append(f"asset criticality {criticality}")

        imminent = any(
            p.status == "OK"
            and p.threshold_crossing_seconds is not None
            and p.threshold_crossing_seconds <= policy.imminent_crossing_seconds
            for p in prognostics
        )
        if imminent:
            tier += policy.tier_adjustments.imminent_threshold_crossing
            adjustments.append("imminent forecasted threshold crossing")

        tier = max(0, min(tier, 3))
        priority = policy.priority_for_tier(tier)
        if adjustments:
            limitations.append(f"Priority adjusted upward for: {', '.join(adjustments)}.")

    window = policy.priority_window_map[priority]
    human_review = action not in policy.non_physical_actions
    risk = policy.risk_language[condition.condition_type]

    # A decision can never be more confident than the condition assessment it is based on.
    confidence = condition.confidence
    if not prognostics or all(p.status == "NO_RELIABLE_FORECAST" for p in prognostics):
        limitations.append("No reliable forecast is available to inform urgency.")

    evidence: dict[str, object] = {
        "what_should_i_do": action,
        "why": condition.what_is_happening,
        "when": window,
        "risk_if_deferred": risk,
        "confidence": confidence,
        "based_on_condition_id": condition.id,
        "missing_data": list(limitations),
    }

    return DecisionResult(
        priority=priority,
        recommended_action=action,
        recommended_window=window,
        risk_if_deferred=risk,
        human_review_required=human_review,
        confidence=confidence,
        evidence=evidence,
        limitations=tuple(limitations),
        expires_in_seconds=policy.expiry_seconds_by_priority[priority],
    )
