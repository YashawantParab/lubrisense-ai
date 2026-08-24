"""Pure energy-portfolio-bucket derivation — no I/O, no database (Portfolio Intelligence
Pass 1, ADR-177, docs/PORTFOLIO_INTELLIGENCE.md §"energy portfolio semantics").

Combines a machine's *current* `EnergyAssessment`/`LubricationEnergyAttribution` state
with its most recent `EnergyOutcomeVerification` (if any) into ONE bucket describing
where the machine sits in the energy-efficiency story — never a separate, conflicting
pair of numbers a reader has to reconcile themselves.

Preserves two required, load-bearing distinctions verbatim from Pass 2/3:
- An asset with only `POSSIBLE`/`MODERATE`/`STRONG` attribution and no completed
  intervention is `ATTRIBUTION_SUPPORTED_OPPORTUNITY` — an opportunity, never a recovery.
- `PROBABLE_RECOVERY` is never folded into `QUALIFIED_ENERGY_RECOVERY` — see
  `EnergyPortfolioBucket`'s own docstring.
"""

from __future__ import annotations

from app.domain.enums import (
    AttributionLevel,
    EnergyAssessmentStatus,
    EnergyOutcomeStatus,
    EnergyPortfolioBucket,
)

#: Energy-assessment statuses that carry no reliable actual/expected comparison at all.
_NO_DATA_STATUSES = frozenset(
    {
        EnergyAssessmentStatus.INSUFFICIENT_DATA,
        EnergyAssessmentStatus.INSUFFICIENT_BASELINE,
        EnergyAssessmentStatus.DATA_QUALITY_LIMITED,
    }
)


def derive_energy_bucket(
    *,
    energy_status: EnergyAssessmentStatus | None,
    attribution_level: AttributionLevel | None,
    latest_outcome_status: EnergyOutcomeStatus | None,
    has_completed_maintenance: bool,
) -> EnergyPortfolioBucket:
    """`has_completed_maintenance` is true when at least one `MaintenanceCase.state ==
    COMPLETED` exists for the machine (a simplification: not filtered by
    `determine_maintenance_relevance`'s structured-action check, since that requires a
    per-case `MaintenanceAction` join this portfolio-wide bucket derivation intentionally
    keeps cheap — documented in docs/PORTFOLIO_INTELLIGENCE.md)."""
    if latest_outcome_status is not None:
        if latest_outcome_status == EnergyOutcomeStatus.QUALIFIED_RECOVERY:
            return EnergyPortfolioBucket.QUALIFIED_ENERGY_RECOVERY
        if latest_outcome_status == EnergyOutcomeStatus.PROBABLE_RECOVERY:
            return EnergyPortfolioBucket.INCONCLUSIVE_OUTCOME
        if latest_outcome_status == EnergyOutcomeStatus.DETERIORATED:
            return EnergyPortfolioBucket.OUTCOME_DETERIORATED
        if latest_outcome_status == EnergyOutcomeStatus.INCONCLUSIVE:
            return EnergyPortfolioBucket.INCONCLUSIVE_OUTCOME
        # NO_MATERIAL_CHANGE / INSUFFICIENT_DATA fall through to the current-state
        # classification below — the maintenance-specific view
        # (MaintenanceOutcomeBucket) already has a dedicated bucket for these; the
        # energy-portfolio view instead describes the asset by its current state.

    if latest_outcome_status is None and has_completed_maintenance:
        return EnergyPortfolioBucket.OUTCOME_AWAITING_VERIFICATION

    if energy_status is None or energy_status in _NO_DATA_STATUSES:
        return EnergyPortfolioBucket.INSUFFICIENT_ENERGY_DATA
    if energy_status != EnergyAssessmentStatus.ELEVATED_ENERGY_DEMAND:
        return EnergyPortfolioBucket.NORMAL_ENERGY_BEHAVIOR
    if attribution_level is not None and attribution_level != AttributionLevel.NO_EVIDENCE:
        return EnergyPortfolioBucket.ATTRIBUTION_SUPPORTED_OPPORTUNITY
    return EnergyPortfolioBucket.ACTIVE_ELEVATED_ENERGY
