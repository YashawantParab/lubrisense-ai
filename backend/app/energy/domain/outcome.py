"""Pure energy-outcome derivation — no I/O, no database, mirroring
`app.energy.domain.attribution`'s own "pure deterministic policy, explainable evidence
lists, no hidden magic numbers" shape (Lubrication Efficiency Intelligence, Pass 3 —
docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md §9, ADR-176).

Builds no new statistical method for "was this window elevated": `_elevated_rank` reuses
`app.baselines.domain.deviation.compute_deviation`'s own `DeviationClassification`
directly (WITHIN_EXPECTED_RANGE / MILD_DEVIATION / STRONG_DEVIATION), the exact same
MAD-based, policy-configured tiers `EnergyAssessmentStatus.ELEVATED_ENERGY_DEMAND` is
already derived from — never a newly-invented percentage threshold for "materially
different". The only genuinely new numeric policy this module introduces is the window
-selection policy in `app.energy.domain.comparability` (sample/duration minimums), which
is deliberately named and documented rather than hidden inline.

Claim-hierarchy discipline (design doc §"claim hierarchy") and the temporal-attribution
-integrity rule (design doc §"temporal attribution integrity") are both enforced here:
`derive_energy_outcome` never mutates its `pre_attribution_level` input, only reads it —
the caller is responsible for passing in a value already frozen from the historical
`LubricationEnergyAttribution` row computed *before* the intervention, never a live
re-read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.domain.enums import (
    AttributionLevel,
    ComparabilityStatus,
    DeviationClassification,
    EnergyEstimateStatus,
    EnergyOutcomeStatus,
    LubricationAssociationStatus,
    MaintenanceActionType,
    RecommendedAction,
)

POLICY_VERSION = "1"

#: Structured, relevant maintenance actions — a real corrective step touching the
#: lubrication path or a lubrication-related bearing condition (design doc §"maintenance
#: relevance"). Deliberately excludes `INSPECTED`/`NO_ACTION_REQUIRED` — a generic
#: inspection with no corrective action taken is not itself a qualifying intervention.
_RELEVANT_RECOMMENDED_ACTIONS = frozenset(
    {
        RecommendedAction.INSPECT_LUBRICATION_PATH,
        RecommendedAction.INSPECT_DISTRIBUTOR,
        RecommendedAction.CHECK_RESERVOIR,
        RecommendedAction.CHECK_PUMP,
        RecommendedAction.INSPECT_BEARING,
    }
)
_RELEVANT_ACTION_TYPES = frozenset(
    {
        MaintenanceActionType.CLEANED,
        MaintenanceActionType.REFILLED,
        MaintenanceActionType.COMPONENT_REPLACED,
        MaintenanceActionType.ADJUSTMENT_RECOMMENDED,
    }
)


def determine_maintenance_relevance(
    recommended_action: RecommendedAction, action_types: tuple[MaintenanceActionType, ...]
) -> tuple[bool, str | None]:
    """Structured-field relevance check (never loose keyword matching over free-text
    notes) — design doc §"maintenance relevance"."""
    if recommended_action not in _RELEVANT_RECOMMENDED_ACTIONS:
        return False, (
            f"Recommended action ({recommended_action.value}) is not a lubrication- or "
            "mechanical-condition-relevant action."
        )
    if not any(a in _RELEVANT_ACTION_TYPES for a in action_types):
        return False, (
            "No recorded maintenance action performed a lubrication- or mechanical"
            "-condition-relevant corrective step."
        )
    return True, None


def _elevated_rank(classification: DeviationClassification, residual_kw: float | None) -> int:
    """0 = not showing excess demand, 1 = mild excess, 2 = strong excess. A negative or
    zero residual is never "excess demand" regardless of classification tier — direction
    matters, not just magnitude (mirrors `app.energy.domain.residual.determine_status`'s
    own reasoning)."""
    if residual_kw is None or residual_kw <= 0:
        return 0
    if classification == DeviationClassification.STRONG_DEVIATION:
        return 2
    if classification == DeviationClassification.MILD_DEVIATION:
        return 1
    return 0


#: `DeviationClassification` has only three tiers, so two elevated windows can both land
#: on STRONG_DEVIATION even when the underlying residual grew substantially between them
#: (the tier saturates). This named, documented relative-change threshold is the
#: deliberately narrow tiebreaker used ONLY when `pre_rank == post_rank > 0` — never the
#: primary classification mechanism, which stays the reused deviation tiers.
MATERIAL_CHANGE_RELATIVE_THRESHOLD = 0.15


def classify_energy_outcome(
    *,
    comparability_status: ComparabilityStatus,
    pre_classification: DeviationClassification,
    pre_residual_kw: float | None,
    post_classification: DeviationClassification,
    post_residual_kw: float | None,
) -> EnergyOutcomeStatus:
    if comparability_status == ComparabilityStatus.INSUFFICIENT_DATA:
        return EnergyOutcomeStatus.INSUFFICIENT_DATA
    if comparability_status == ComparabilityStatus.NOT_COMPARABLE:
        return EnergyOutcomeStatus.INCONCLUSIVE

    pre_rank = _elevated_rank(pre_classification, pre_residual_kw)
    post_rank = _elevated_rank(post_classification, post_residual_kw)

    if pre_rank == 0:
        # Nothing elevated before the intervention — there is no excess-energy story to
        # verify a recovery against, regardless of what the post-window shows.
        return EnergyOutcomeStatus.NO_MATERIAL_CHANGE
    if post_rank == 0:
        return (
            EnergyOutcomeStatus.QUALIFIED_RECOVERY
            if comparability_status == ComparabilityStatus.COMPARABLE
            else EnergyOutcomeStatus.PROBABLE_RECOVERY
        )
    if post_rank < pre_rank:
        return EnergyOutcomeStatus.PROBABLE_RECOVERY
    if post_rank > pre_rank:
        return EnergyOutcomeStatus.DETERIORATED

    # post_rank == pre_rank > 0: same classification tier (most commonly both saturated
    # at STRONG_DEVIATION) — the tiers alone cannot tell "worse" from "better" from
    # "unchanged" here, so fall back to the residual magnitude itself.
    assert pre_residual_kw is not None and post_residual_kw is not None
    relative_change = (pre_residual_kw - post_residual_kw) / pre_residual_kw
    if relative_change <= -MATERIAL_CHANGE_RELATIVE_THRESHOLD:
        return EnergyOutcomeStatus.DETERIORATED
    if relative_change >= MATERIAL_CHANGE_RELATIVE_THRESHOLD:
        return EnergyOutcomeStatus.PROBABLE_RECOVERY
    return EnergyOutcomeStatus.NO_MATERIAL_CHANGE


def integrate_avoided_energy_kwh(
    pre_reference_residual_kw: float, post_residual_samples: list[tuple[datetime, float]]
) -> float:
    """Trapezoidal integration of positive contextual-residual improvement
    (`pre_reference_residual_kw - post_residual_kw(t)`, clamped at zero) across the
    qualifying post-intervention window only. Never negative — each *sample's own*
    improvement value is clamped at zero before trapezoidal interpolation runs on the
    clamped endpoints, so a post sample that momentarily reads worse than the
    pre-intervention average never *subtracts* from the running total; it only fails to
    add to it. This is a deliberate simplification, not an exact-crossing method: if the
    sign changes strictly *between* two consecutive samples, the clamped-endpoint
    trapezoid can slightly overstate the true sub-interval area (see
    `test_outcome_policy.py`'s own worked example) rather than solving for the exact
    zero-crossing instant — acceptable given this platform's dense real telemetry
    sampling, where the segment between two consecutive samples is short. Handles
    irregular timestamps directly (no resampling of the underlying signal — only the
    integral itself uses linear interpolation between consecutive real samples)."""
    if len(post_residual_samples) < 2:
        return 0.0
    ordered = sorted(post_residual_samples, key=lambda pair: pair[0])
    total_kwh = 0.0
    for (t0, r0), (t1, r1) in zip(ordered, ordered[1:], strict=False):
        improvement0 = max(0.0, pre_reference_residual_kw - r0)
        improvement1 = max(0.0, pre_reference_residual_kw - r1)
        dt_hours = (t1 - t0).total_seconds() / 3600.0
        if dt_hours <= 0:
            continue
        total_kwh += 0.5 * (improvement0 + improvement1) * dt_hours
    return total_kwh


def determine_energy_estimate_status(
    energy_outcome_status: EnergyOutcomeStatus,
) -> EnergyEstimateStatus:
    if energy_outcome_status == EnergyOutcomeStatus.QUALIFIED_RECOVERY:
        return EnergyEstimateStatus.ESTIMATED
    if energy_outcome_status == EnergyOutcomeStatus.INSUFFICIENT_DATA:
        return EnergyEstimateStatus.INSUFFICIENT_DATA
    if energy_outcome_status == EnergyOutcomeStatus.INCONCLUSIVE:
        return EnergyEstimateStatus.NOT_COMPARABLE
    return EnergyEstimateStatus.NOT_QUALIFIED


def derive_lubrication_association(
    *,
    energy_outcome_status: EnergyOutcomeStatus,
    maintenance_relevant: bool,
    pre_attribution_level: AttributionLevel | None,
) -> tuple[LubricationAssociationStatus, str]:
    """Claim-hierarchy policy (design doc §"claim hierarchy") — never skips a level, and
    (temporal-integrity rule, §"temporal attribution integrity") never lets a good
    post-maintenance outcome upgrade what the platform believed about attribution
    *before* the intervention: `pre_attribution_level` is read here exactly as given, a
    frozen historical value the caller resolved before this function was ever called."""
    if energy_outcome_status not in (
        EnergyOutcomeStatus.QUALIFIED_RECOVERY,
        EnergyOutcomeStatus.PROBABLE_RECOVERY,
    ):
        return (
            LubricationAssociationStatus.NOT_APPLICABLE,
            "No qualifying energy recovery was observed to associate with lubrication "
            "condition.",
        )

    if energy_outcome_status == EnergyOutcomeStatus.PROBABLE_RECOVERY:
        return (
            LubricationAssociationStatus.OBSERVED_ENERGY_CHANGE,
            "Contextual energy residual decreased after the intervention, though the "
            "comparison did not meet the full qualification bar.",
        )

    if not maintenance_relevant:
        return (
            LubricationAssociationStatus.QUALIFIED_ENERGY_RECOVERY,
            "Under comparable operating conditions, excess energy demand decreased "
            "after the intervention. The completed maintenance action was not "
            "structurally relevant to lubrication or mechanical-condition, so this "
            "recovery is not associated with lubrication.",
        )

    if pre_attribution_level is None or pre_attribution_level == AttributionLevel.NO_EVIDENCE:
        return (
            LubricationAssociationStatus.QUALIFIED_ENERGY_RECOVERY,
            "Under comparable operating conditions, excess energy demand decreased "
            "after a relevant intervention. No pre-intervention lubrication-attribution "
            "evidence supported a lubrication-related hypothesis at the time, so this "
            "recovery is not described as lubrication-associated.",
        )

    return (
        LubricationAssociationStatus.LUBRICATION_ASSOCIATED_RECOVERY,
        "Under comparable operating conditions, excess energy demand decreased after a "
        "relevant intervention. The observed recovery is consistent with the previously "
        f"{pre_attribution_level.value} lubrication-related hypothesis and the "
        "intervention performed — an association, not proof of causation.",
    )


@dataclass(frozen=True)
class EnergyOutcomeExplanation:
    energy_outcome_status: EnergyOutcomeStatus
    energy_estimate_status: EnergyEstimateStatus
    estimated_avoided_energy_kwh: float | None
    lubrication_association_status: LubricationAssociationStatus
    supporting_evidence: tuple[str, ...] = field(default_factory=tuple)
    contradicting_evidence: tuple[str, ...] = field(default_factory=tuple)
    limiting_factors: tuple[str, ...] = field(default_factory=tuple)
    alternative_explanations: tuple[str, ...] = field(default_factory=tuple)
