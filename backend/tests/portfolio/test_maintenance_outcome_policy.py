"""Pure tests for `app.portfolio.domain.maintenance_outcome` (Portfolio Intelligence
Pass 1, ADR-177)."""

from __future__ import annotations

from app.domain.enums import EnergyOutcomeStatus, MaintenanceOutcomeBucket, MaintenanceState
from app.portfolio.domain.maintenance_outcome import derive_maintenance_outcome_bucket


def test_non_terminal_states_are_open_action() -> None:
    for state in (
        MaintenanceState.REVIEW_REQUIRED,
        MaintenanceState.NOT_STARTED,
        MaintenanceState.PLANNED,
        MaintenanceState.IN_PROGRESS,
        MaintenanceState.AWAITING_VERIFICATION,
    ):
        result = derive_maintenance_outcome_bucket(
            maintenance_state=state, energy_outcome_status=None
        )
        assert result == MaintenanceOutcomeBucket.OPEN_ACTION


def test_cancelled_is_excluded_not_forced_into_a_bucket() -> None:
    result = derive_maintenance_outcome_bucket(
        maintenance_state=MaintenanceState.CANCELLED, energy_outcome_status=None
    )
    assert result is None


def test_completed_no_outcome_yet_is_not_assessed() -> None:
    result = derive_maintenance_outcome_bucket(
        maintenance_state=MaintenanceState.COMPLETED, energy_outcome_status=None
    )
    assert result == MaintenanceOutcomeBucket.COMPLETED_OUTCOME_NOT_ASSESSED


def test_completion_is_never_automatic_success() -> None:
    """Completion alone, without inspecting the actual energy_outcome_status, must never
    default to a positive bucket."""
    result = derive_maintenance_outcome_bucket(
        maintenance_state=MaintenanceState.COMPLETED,
        energy_outcome_status=EnergyOutcomeStatus.DETERIORATED,
    )
    assert result == MaintenanceOutcomeBucket.COMPLETED_DETERIORATED
    assert result != MaintenanceOutcomeBucket.COMPLETED_QUALIFIED_RECOVERY


def test_qualified_recovery_maps_correctly() -> None:
    result = derive_maintenance_outcome_bucket(
        maintenance_state=MaintenanceState.COMPLETED,
        energy_outcome_status=EnergyOutcomeStatus.QUALIFIED_RECOVERY,
    )
    assert result == MaintenanceOutcomeBucket.COMPLETED_QUALIFIED_RECOVERY


def test_probable_recovery_gets_its_own_bucket_not_qualified() -> None:
    result = derive_maintenance_outcome_bucket(
        maintenance_state=MaintenanceState.COMPLETED,
        energy_outcome_status=EnergyOutcomeStatus.PROBABLE_RECOVERY,
    )
    assert result == MaintenanceOutcomeBucket.COMPLETED_PROBABLE_RECOVERY
    assert result != MaintenanceOutcomeBucket.COMPLETED_QUALIFIED_RECOVERY
    assert result != MaintenanceOutcomeBucket.COMPLETED_INCONCLUSIVE


def test_no_material_change_maps_correctly() -> None:
    result = derive_maintenance_outcome_bucket(
        maintenance_state=MaintenanceState.COMPLETED,
        energy_outcome_status=EnergyOutcomeStatus.NO_MATERIAL_CHANGE,
    )
    assert result == MaintenanceOutcomeBucket.COMPLETED_NO_MATERIAL_CHANGE


def test_inconclusive_and_insufficient_data_both_map_to_completed_inconclusive() -> None:
    for status in (EnergyOutcomeStatus.INCONCLUSIVE, EnergyOutcomeStatus.INSUFFICIENT_DATA):
        result = derive_maintenance_outcome_bucket(
            maintenance_state=MaintenanceState.COMPLETED, energy_outcome_status=status
        )
        assert result == MaintenanceOutcomeBucket.COMPLETED_INCONCLUSIVE
