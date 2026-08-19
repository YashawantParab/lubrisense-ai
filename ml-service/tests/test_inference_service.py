import uuid
from datetime import UTC, datetime
from pathlib import Path

from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LogisticRegression

from ml_service.domain.dataset import DatasetSample, SplitName
from ml_service.domain.feature_snapshot import FeatureSnapshot
from ml_service.domain.inference import InferenceStatus
from ml_service.domain.labels import FailureLabel
from ml_service.domain.model_metadata import ModelLifecycleState, ModelMetadata, ModelType
from ml_service.inference.service import InferenceService
from ml_service.models.anomaly import AnomalyModelArtifact
from ml_service.models.classifier import ClassifierModelArtifact
from ml_service.registry.registry import ModelRegistry
from ml_service.training.preprocessing import Preprocessor

TENANT = uuid.uuid4()
MACHINE = uuid.uuid4()
REQUIRED = ("pressure.current", "pump_current.current")


def _train_sample(pressure: float, pump_current: float, label: FailureLabel) -> DatasetSample:
    return DatasetSample(
        feature_vector_id=uuid.uuid4(),
        run_id="r0",
        tenant_id=TENANT,
        machine_id=MACHINE,
        asset_code="L1-7B43-M000",
        as_of_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        feature_set="FAILURE_CLASSIFICATION_V1",
        feature_set_version="1.0.2",
        feature_values={"pressure.current": pressure, "pump_current.current": pump_current},
        missing_features=(),
        quality_summary={},
        label=label,
        source_scenario_type=None,
        ground_truth_severity=0.0,
        split=SplitName.TRAIN,
    )


def _snapshot(feature_values: dict, missing: tuple[str, ...] = ()) -> FeatureSnapshot:
    return FeatureSnapshot(
        feature_vector_id=uuid.uuid4(),
        as_of_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        feature_set="FAILURE_CLASSIFICATION_V1",
        feature_set_version="1.0.2",
        feature_values=feature_values,
        missing_features=missing,
        quality_summary={"trusted_fraction": 1.0},
    )


def _build_classifier_artifact() -> ClassifierModelArtifact:
    train = [_train_sample(5.0, 3.0, FailureLabel.NORMAL) for _ in range(15)] + [
        _train_sample(25.0, 12.0, FailureLabel.RESTRICTION) for _ in range(15)
    ]
    pre = Preprocessor(numeric_features=REQUIRED, categorical_features=())
    pre.fit(train)
    x = pre.transform(train)
    y = [s.label.value for s in train]
    estimator = LogisticRegression().fit(x, y)
    return ClassifierModelArtifact(
        estimator=estimator,
        preprocessor=pre,
        feature_names=REQUIRED,
        categorical_features=(),
        minimum_required_features=REQUIRED,
        class_order=tuple(estimator.classes_),
        unknown_confidence_threshold=0.9,  # deliberately high, to exercise UNKNOWN path
    )


def _build_anomaly_artifact() -> AnomalyModelArtifact:
    train = [_train_sample(5.0 + i * 0.01, 3.0 + i * 0.01, FailureLabel.NORMAL) for i in range(30)]
    pre = Preprocessor(numeric_features=REQUIRED, categorical_features=())
    pre.fit(train)
    x = pre.transform(train)
    estimator = IsolationForest(n_estimators=50, random_state=1).fit(x)
    return AnomalyModelArtifact(
        estimator=estimator,
        preprocessor=pre,
        numeric_features=REQUIRED,
        minimum_required_features=REQUIRED,
        threshold=0.0,
    )


def _metadata(model_id: str, model_type: ModelType, thresholds: dict) -> ModelMetadata:
    return ModelMetadata(
        model_id=model_id,
        model_version="1.0.0",
        model_type=model_type,
        training_time=datetime(2026, 1, 1, tzinfo=UTC),
        dataset_id="TEST",
        dataset_version="1.0.0",
        feature_set="FAILURE_CLASSIFICATION_V1",
        feature_set_version="1.0.2",
        features=REQUIRED,
        hyperparameters={},
        metrics={},
        thresholds=thresholds,
        seed=1,
        code_version="0.1.0",
        status=ModelLifecycleState.VALIDATED,
        limitations=(),
        minimum_required_features=REQUIRED,
    )


def test_classification_insufficient_features_when_required_missing(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    artifact = _build_classifier_artifact()
    registry.register(
        artifact,
        _metadata(
            "FAILURE_CLASSIFICATION_V1", ModelType.CLASSIFIER_BASELINE_LOGISTIC_REGRESSION, {}
        ),
    )
    service = InferenceService(registry)

    snapshot = _snapshot(
        {"pressure.current": 5.0, "pump_current.current": None}, missing=("pump_current.current",)
    )
    result = service.infer_classification(snapshot, "FAILURE_CLASSIFICATION_V1", "1.0.0")
    assert result.status == InferenceStatus.INSUFFICIENT_FEATURES
    assert result.predicted_class is None


def test_classification_low_confidence_returns_unknown(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    artifact = _build_classifier_artifact()
    registry.register(
        artifact,
        _metadata(
            "FAILURE_CLASSIFICATION_V1", ModelType.CLASSIFIER_BASELINE_LOGISTIC_REGRESSION, {}
        ),
    )
    service = InferenceService(registry)

    snapshot = _snapshot({"pressure.current": 15.0, "pump_current.current": 7.5})
    result = service.infer_classification(snapshot, "FAILURE_CLASSIFICATION_V1", "1.0.0")
    assert result.status == InferenceStatus.UNKNOWN
    assert result.predicted_class == FailureLabel.UNKNOWN.value


def test_classification_is_deterministic_for_same_input(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    artifact = _build_classifier_artifact()
    registry.register(
        artifact,
        _metadata(
            "FAILURE_CLASSIFICATION_V1",
            ModelType.CLASSIFIER_BASELINE_LOGISTIC_REGRESSION,
            {"moderate": 0.5, "high": 0.75},
        ),
    )
    service = InferenceService(registry)
    snapshot = _snapshot({"pressure.current": 5.0, "pump_current.current": 3.0})

    result1 = service.infer_classification(snapshot, "FAILURE_CLASSIFICATION_V1", "1.0.0")
    result2 = service.infer_classification(snapshot, "FAILURE_CLASSIFICATION_V1", "1.0.0")
    assert result1.predicted_class == result2.predicted_class
    assert result1.class_probabilities == result2.class_probabilities


def test_anomaly_output_never_labeled_failure(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    artifact = _build_anomaly_artifact()
    artifact.threshold = -0.05
    registry.register(
        artifact, _metadata("LUBRICATION_ANOMALY_V1", ModelType.ANOMALY_ISOLATION_FOREST, {})
    )
    service = InferenceService(registry)

    snapshot = _snapshot({"pressure.current": 90.0, "pump_current.current": 45.0})
    result = service.infer_anomaly(snapshot, "LUBRICATION_ANOMALY_V1", "1.0.0")
    assert result.status == InferenceStatus.OK
    assert result.anomalous is True
    result_dict = result.to_dict()
    assert "failure" not in str(result_dict).lower()


def test_anomaly_insufficient_features(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    artifact = _build_anomaly_artifact()
    registry.register(
        artifact, _metadata("LUBRICATION_ANOMALY_V1", ModelType.ANOMALY_ISOLATION_FOREST, {})
    )
    service = InferenceService(registry)

    snapshot = _snapshot({"pressure.current": None, "pump_current.current": None}, missing=REQUIRED)
    result = service.infer_anomaly(snapshot, "LUBRICATION_ANOMALY_V1", "1.0.0")
    assert result.status == InferenceStatus.INSUFFICIENT_FEATURES
    assert result.anomaly_score is None
