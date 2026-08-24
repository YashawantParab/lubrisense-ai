"""Tests for `app.energy.domain.evidence.energy_residual_evidence` — confirms the
"observable only" contract: a real `EvidenceItem`-shaped object is produced, but
`condition_hint` is always `None` (fault-agnostic, cannot vote) and no insufficient/
within-range status produces evidence at all."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.domain.enums import BaselineSourceKind, EnergyAssessmentStatus, QualityState
from app.domain.models import EnergyAssessment
from app.energy.domain.evidence import energy_residual_evidence


def _assessment(
    status: EnergyAssessmentStatus,
    *,
    residual_kw: float | None = None,
    residual_pct: float | None = None,
) -> EnergyAssessment:
    return EnergyAssessment(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        machine_id=uuid.uuid4(),
        power_sensor_id=uuid.uuid4(),
        as_of_timestamp=datetime.now(UTC),
        actual_power_kw=55.0,
        expected_power_kw=50.0,
        expected_lower_kw=48.0,
        expected_upper_kw=52.0,
        residual_kw=residual_kw,
        residual_pct=residual_pct,
        status=status,
        data_quality_state=QualityState.TRUSTED,
        baseline_source=BaselineSourceKind.EXACT_CONTEXT,
        baseline_profile_id=uuid.uuid4(),
        operating_state="RUNNING_NORMAL_LOAD",
        engine_version="1",
    )


def test_elevated_energy_demand_produces_evidence() -> None:
    assessment = _assessment(
        EnergyAssessmentStatus.ELEVATED_ENERGY_DEMAND, residual_kw=5.0, residual_pct=10.0
    )
    evidence = energy_residual_evidence(assessment)
    assert evidence is not None
    assert evidence.source_type == "ENERGY_RESIDUAL"
    assert evidence.source_id == str(assessment.id)
    assert evidence.condition_hint is None  # fault-agnostic by construction
    assert evidence.strength == "WEAK"
    assert "+10.0%" in evidence.description


def test_below_expected_range_produces_evidence() -> None:
    assessment = _assessment(
        EnergyAssessmentStatus.BELOW_EXPECTED_RANGE, residual_kw=-5.0, residual_pct=-10.0
    )
    evidence = energy_residual_evidence(assessment)
    assert evidence is not None
    assert "-10.0%" in evidence.description


def test_within_expected_range_produces_no_evidence() -> None:
    assessment = _assessment(
        EnergyAssessmentStatus.WITHIN_EXPECTED_RANGE, residual_kw=0.1, residual_pct=0.2
    )
    assert energy_residual_evidence(assessment) is None


def test_insufficient_baseline_produces_no_evidence() -> None:
    assessment = _assessment(EnergyAssessmentStatus.INSUFFICIENT_BASELINE)
    assert energy_residual_evidence(assessment) is None


def test_insufficient_data_produces_no_evidence() -> None:
    assessment = _assessment(EnergyAssessmentStatus.INSUFFICIENT_DATA)
    assert energy_residual_evidence(assessment) is None


def test_data_quality_limited_produces_no_evidence() -> None:
    assessment = _assessment(EnergyAssessmentStatus.DATA_QUALITY_LIMITED)
    assert energy_residual_evidence(assessment) is None


def test_falls_back_to_kw_when_percentage_unavailable() -> None:
    assessment = _assessment(
        EnergyAssessmentStatus.ELEVATED_ENERGY_DEMAND, residual_kw=5.0, residual_pct=None
    )
    evidence = energy_residual_evidence(assessment)
    assert evidence is not None
    assert "+5.00 kW" in evidence.description
