import uuid
from datetime import UTC, datetime

from ml_service.domain.dataset import DatasetSample, SplitName
from ml_service.domain.labels import FailureLabel
from ml_service.training.preprocessing import Preprocessor

TENANT = uuid.uuid4()
MACHINE = uuid.uuid4()


def _sample(feature_values: dict) -> DatasetSample:
    return DatasetSample(
        feature_vector_id=uuid.uuid4(),
        run_id="r0",
        tenant_id=TENANT,
        machine_id=MACHINE,
        asset_code="L1-7B43-M000",
        as_of_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        feature_set="FAILURE_CLASSIFICATION_V1",
        feature_set_version="1.0.2",
        feature_values=feature_values,
        missing_features=tuple(k for k, v in feature_values.items() if v is None),
        quality_summary={},
        label=FailureLabel.NORMAL,
        source_scenario_type=None,
        ground_truth_severity=0.0,
        split=SplitName.TRAIN,
    )


def test_median_is_fit_only_on_provided_train_samples() -> None:
    train = [_sample({"pressure.current": v}) for v in (1.0, 2.0, 3.0)]
    pre = Preprocessor(numeric_features=("pressure.current",), categorical_features=())
    pre.fit(train)
    assert pre.medians["pressure.current"] == 2.0


def test_missing_value_is_imputed_with_median_and_flagged() -> None:
    train = [_sample({"pressure.current": v}) for v in (1.0, 2.0, 3.0)]
    pre = Preprocessor(numeric_features=("pressure.current",), categorical_features=())
    pre.fit(train)

    missing_sample = _sample({"pressure.current": None})
    x = pre.transform([missing_sample])
    value_col = pre.output_columns.index("pressure.current")
    missing_col = pre.output_columns.index("pressure.current.__missing__")
    assert x[0, value_col] == 2.0
    assert x[0, missing_col] == 1.0


def test_observed_zero_is_not_confused_with_missing() -> None:
    train = [_sample({"pressure.current": v}) for v in (1.0, 2.0, 3.0)]
    pre = Preprocessor(numeric_features=("pressure.current",), categorical_features=())
    pre.fit(train)

    zero_sample = _sample({"pressure.current": 0.0})
    x = pre.transform([zero_sample])
    value_col = pre.output_columns.index("pressure.current")
    missing_col = pre.output_columns.index("pressure.current.__missing__")
    assert x[0, value_col] == 0.0
    assert x[0, missing_col] == 0.0


def test_boolean_feature_encoded_as_one_zero() -> None:
    train = [_sample({"cycle.success": True}), _sample({"cycle.success": False})]
    pre = Preprocessor(numeric_features=("cycle.success",), categorical_features=())
    pre.fit(train)
    x = pre.transform([_sample({"cycle.success": True})])
    col = pre.output_columns.index("cycle.success")
    assert x[0, col] == 1.0


def test_categorical_unseen_value_falls_into_other_bucket() -> None:
    train = [_sample({"context.load_bucket": v}) for v in ("LOW", "NORMAL", "HIGH")]
    pre = Preprocessor(numeric_features=(), categorical_features=("context.load_bucket",))
    pre.fit(train)

    unseen = _sample({"context.load_bucket": "NEVER_SEEN_AT_TRAIN_TIME"})
    x = pre.transform([unseen])
    other_col = pre.output_columns.index("context.load_bucket=__OTHER__")
    assert x[0, other_col] == 1.0


def test_categorical_missing_value_falls_into_missing_bucket() -> None:
    train = [_sample({"context.load_bucket": v}) for v in ("LOW", "NORMAL")]
    pre = Preprocessor(numeric_features=(), categorical_features=("context.load_bucket",))
    pre.fit(train)

    missing = _sample({"context.load_bucket": None})
    x = pre.transform([missing])
    missing_col = pre.output_columns.index("context.load_bucket=__MISSING__")
    assert x[0, missing_col] == 1.0


def test_missing_feature_count_helper() -> None:
    pre = Preprocessor(numeric_features=(), categorical_features=())
    sample = _sample({"a": 1.0, "b": None, "c": None})
    assert pre.missing_feature_count(sample, ("a", "b", "c")) == 2
