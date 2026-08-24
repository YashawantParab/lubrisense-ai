"""Pure tests for `app.portfolio.domain.data_trust` (Portfolio Intelligence Pass 1,
ADR-177)."""

from __future__ import annotations

from app.domain.enums import DataTrustCategory, QualityState
from app.portfolio.domain.data_trust import derive_data_trust_category, overall_quality_state


class TestOverallQualityState:
    def test_empty_is_no_trusted_data(self) -> None:
        assert overall_quality_state([]) == "NO_TRUSTED_DATA"

    def test_all_unusable_is_no_trusted_data(self) -> None:
        assert (
            overall_quality_state([QualityState.UNUSABLE, QualityState.UNUSABLE])
            == "NO_TRUSTED_DATA"
        )

    def test_any_caution_is_caution(self) -> None:
        result = overall_quality_state(
            [QualityState.TRUSTED, QualityState.USABLE_WITH_CAUTION, QualityState.TRUSTED]
        )
        assert result == "CAUTION"

    def test_mixed_trusted_and_unusable_without_caution_is_trusted(self) -> None:
        result = overall_quality_state([QualityState.TRUSTED, QualityState.UNUSABLE])
        assert result == "TRUSTED"

    def test_all_trusted_is_trusted(self) -> None:
        assert overall_quality_state([QualityState.TRUSTED, QualityState.TRUSTED]) == "TRUSTED"


class TestDeriveDataTrustCategory:
    def test_trusted_no_workflow_is_decision_evidence_trusted(self) -> None:
        result = derive_data_trust_category(overall_quality="TRUSTED", has_open_workflow=False)
        assert result == DataTrustCategory.DECISION_EVIDENCE_TRUSTED

    def test_trusted_with_workflow_is_still_trusted(self) -> None:
        """A healthy, trusted sensor set never becomes 'blocked' just because there's an
        open workflow — action-blocking requires an actual data-quality limitation."""
        result = derive_data_trust_category(overall_quality="TRUSTED", has_open_workflow=True)
        assert result == DataTrustCategory.DECISION_EVIDENCE_TRUSTED

    def test_caution_no_workflow_is_confidence_reduced(self) -> None:
        result = derive_data_trust_category(overall_quality="CAUTION", has_open_workflow=False)
        assert result == DataTrustCategory.CONFIDENCE_REDUCED

    def test_caution_with_workflow_is_action_blocked(self) -> None:
        result = derive_data_trust_category(overall_quality="CAUTION", has_open_workflow=True)
        assert result == DataTrustCategory.ACTION_BLOCKED

    def test_no_trusted_data_no_workflow_is_assessment_blocked(self) -> None:
        result = derive_data_trust_category(
            overall_quality="NO_TRUSTED_DATA", has_open_workflow=False
        )
        assert result == DataTrustCategory.ASSESSMENT_BLOCKED

    def test_no_trusted_data_with_workflow_is_action_blocked(self) -> None:
        result = derive_data_trust_category(
            overall_quality="NO_TRUSTED_DATA", has_open_workflow=True
        )
        assert result == DataTrustCategory.ACTION_BLOCKED
