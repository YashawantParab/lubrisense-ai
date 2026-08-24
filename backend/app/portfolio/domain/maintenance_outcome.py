"""Pure per-`MaintenanceCase` outcome-bucket derivation — no I/O, no database (Portfolio
Intelligence Pass 1, ADR-177, docs/PORTFOLIO_INTELLIGENCE.md §"maintenance outcome
semantics"). Completion is never represented as automatic success — see
`MaintenanceOutcomeBucket`'s own docstring for the one principled addition beyond the six
literally-requested buckets.
"""

from __future__ import annotations

from app.domain.enums import EnergyOutcomeStatus, MaintenanceOutcomeBucket, MaintenanceState

_STATUS_TO_BUCKET: dict[EnergyOutcomeStatus, MaintenanceOutcomeBucket] = {
    EnergyOutcomeStatus.QUALIFIED_RECOVERY: MaintenanceOutcomeBucket.COMPLETED_QUALIFIED_RECOVERY,
    EnergyOutcomeStatus.PROBABLE_RECOVERY: MaintenanceOutcomeBucket.COMPLETED_PROBABLE_RECOVERY,
    EnergyOutcomeStatus.NO_MATERIAL_CHANGE: MaintenanceOutcomeBucket.COMPLETED_NO_MATERIAL_CHANGE,
    EnergyOutcomeStatus.DETERIORATED: MaintenanceOutcomeBucket.COMPLETED_DETERIORATED,
    EnergyOutcomeStatus.INCONCLUSIVE: MaintenanceOutcomeBucket.COMPLETED_INCONCLUSIVE,
    EnergyOutcomeStatus.INSUFFICIENT_DATA: MaintenanceOutcomeBucket.COMPLETED_INCONCLUSIVE,
}


def derive_maintenance_outcome_bucket(
    *,
    maintenance_state: MaintenanceState,
    energy_outcome_status: EnergyOutcomeStatus | None,
) -> MaintenanceOutcomeBucket | None:
    """`None` for a `CANCELLED` case — a cancelled case was never completed and is not
    "open" either; callers exclude it from maintenance-outcome counts entirely rather
    than forcing it into either bucket (see docs/PORTFOLIO_INTELLIGENCE.md)."""
    if maintenance_state == MaintenanceState.CANCELLED:
        return None
    if maintenance_state != MaintenanceState.COMPLETED:
        return MaintenanceOutcomeBucket.OPEN_ACTION
    if energy_outcome_status is None:
        return MaintenanceOutcomeBucket.COMPLETED_OUTCOME_NOT_ASSESSED
    return _STATUS_TO_BUCKET[energy_outcome_status]
