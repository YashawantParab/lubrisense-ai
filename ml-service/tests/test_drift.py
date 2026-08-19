import uuid
from datetime import UTC, datetime

from ml_service.domain.dataset import DatasetSample, SplitName
from ml_service.domain.labels import FailureLabel
from ml_service.monitoring.drift import (
    compute_drift_report,
    population_stability_index,
    psi_severity,
)


def _sample(value: float, missing: tuple[str, ...] = ()) -> DatasetSample:
    return DatasetSample(
        feature_vector_id=uuid.uuid4(),
        run_id="run-1",
        tenant_id=uuid.uuid4(),
        machine_id=uuid.uuid4(),
        asset_code="L1-TEST",
        as_of_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        feature_set="TEST_SET",
        feature_set_version="1.0.0",
        feature_values={"pressure.current": value},
        missing_features=missing,
        quality_summary={},
        label=FailureLabel.NORMAL,
        source_scenario_type=None,
        ground_truth_severity=0.0,
        split=SplitName.TRAIN,
    )


def test_psi_is_near_zero_for_identical_distributions() -> None:
    reference = [float(i % 20) for i in range(200)]
    current = [float(i % 20) for i in range(200)]
    psi = population_stability_index(reference, current, buckets=10)
    assert psi is not None
    assert psi < 0.01
    assert psi_severity(psi) == "NO_MEANINGFUL_SHIFT"


def test_psi_flags_a_clear_distribution_shift() -> None:
    reference = [float(i % 20) for i in range(200)]
    current = [float(100 + i % 20) for i in range(200)]
    psi = population_stability_index(reference, current, buckets=10)
    assert psi is not None
    assert psi_severity(psi) == "SUBSTANTIAL_SHIFT"


def test_psi_returns_none_for_insufficient_data() -> None:
    assert population_stability_index([1.0, 2.0], [1.0, 2.0], buckets=10) is None


def test_compute_drift_report_flags_missingness_and_coverage() -> None:
    reference_samples = [_sample(10.0 + i) for i in range(30)]
    current_samples = [
        _sample(10.0 + i, missing=("pressure.current",) if i % 2 == 0 else ())
        for i in range(30)
    ]

    report = compute_drift_report(
        reference_samples, current_samples, feature_names=["pressure.current"]
    )
    assert report.reference_sample_count == 30
    assert report.current_sample_count == 30
    assert report.reference_coverage == 1.0
    assert report.current_coverage < 1.0

    feature_result = report.features[0]
    assert feature_result.reference_missing_rate == 0.0
    assert feature_result.current_missing_rate == 0.5
    assert feature_result.missing_rate_delta == 0.5


def test_drift_report_serializes_to_dict() -> None:
    reference_samples = [_sample(float(i)) for i in range(25)]
    current_samples = [_sample(float(i)) for i in range(25)]
    report = compute_drift_report(
        reference_samples, current_samples, feature_names=["pressure.current"]
    )
    payload = report.to_dict()
    assert payload["reference_sample_count"] == 25
    assert "substantial_shift_features" in payload
