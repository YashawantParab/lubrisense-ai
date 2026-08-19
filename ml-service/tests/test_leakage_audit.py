import uuid
from datetime import UTC, datetime

from ml_service.datasets.leakage_audit import (
    audit_feature_names,
    audit_proxy_leakage,
    run_leakage_audit,
)
from ml_service.domain.dataset import DatasetSample, SplitName
from ml_service.domain.labels import FailureLabel

TENANT = uuid.uuid4()
MACHINE = uuid.uuid4()


def test_audit_feature_names_flags_forbidden_tokens() -> None:
    names = ("pressure.current", "scenario.type", "ground_truth.severity", "cycle.duration")
    flagged = audit_feature_names(names)
    assert "scenario.type" in flagged
    assert "ground_truth.severity" in flagged
    assert "pressure.current" not in flagged
    # "cycle.duration" contains "duration" but not the forbidden "future_duration" token
    assert "cycle.duration" not in flagged


def test_real_phase10_feature_names_pass_clean() -> None:
    names = (
        "pressure.current",
        "quality.trusted_fraction.15m",
        "context.operating_state",
        "rules.restriction_pattern_active",
        "temporal.current_pressure_deviation_duration",
    )
    assert audit_feature_names(names) == ()


def _sample(feature_values: dict, label: FailureLabel, run_id: str) -> DatasetSample:
    return DatasetSample(
        feature_vector_id=uuid.uuid4(),
        run_id=run_id,
        tenant_id=TENANT,
        machine_id=MACHINE,
        asset_code="L1-7B43-M000",
        as_of_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        feature_set="FAILURE_CLASSIFICATION_V1",
        feature_set_version="1.0.2",
        feature_values=feature_values,
        missing_features=(),
        quality_summary={},
        label=label,
        source_scenario_type=None,
        ground_truth_severity=0.0,
        split=SplitName.TRAIN,
    )


def test_proxy_leakage_flags_categorical_that_perfectly_predicts_label() -> None:
    samples = []
    for i in range(10):
        samples.append(
            _sample(
                {"context.operating_state": "RUNNING_HIGH_LOAD"}, FailureLabel.RESTRICTION, f"r{i}"
            )
        )
    for i in range(10):
        samples.append(
            _sample({"context.operating_state": "STOPPED"}, FailureLabel.NORMAL, f"h{i}")
        )

    suspects = audit_proxy_leakage(samples, ("context.operating_state",))
    assert "context.operating_state" in suspects


def test_proxy_leakage_does_not_flag_genuinely_mixed_categorical() -> None:
    samples = []
    for i in range(10):
        label = FailureLabel.RESTRICTION if i % 2 == 0 else FailureLabel.NORMAL
        samples.append(_sample({"context.operating_state": "RUNNING_NORMAL_LOAD"}, label, f"r{i}"))

    suspects = audit_proxy_leakage(samples, ("context.operating_state",))
    assert "context.operating_state" not in suspects


def test_proxy_leakage_ignores_continuous_float_features() -> None:
    samples = [
        _sample(
            {"pressure.current": float(i)},
            FailureLabel.RESTRICTION if i < 5 else FailureLabel.NORMAL,
            f"r{i}",
        )
        for i in range(10)
    ]
    suspects = audit_proxy_leakage(samples, ("pressure.current",))
    assert "pressure.current" not in suspects


def test_run_leakage_audit_passes_on_clean_dataset() -> None:
    samples = [_sample({"pressure.current": 5.0}, FailureLabel.NORMAL, "r0")]
    result = run_leakage_audit(samples, ("pressure.current",))
    assert result.passed is True
    assert result.forbidden_features_found == ()
