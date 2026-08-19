import uuid
from datetime import UTC, datetime

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LogisticRegression

from ml_service.domain.dataset import DatasetSample, SplitName
from ml_service.domain.labels import FailureLabel
from ml_service.explainability.explain import (
    explain_anomaly_prediction,
    explain_classification_prediction,
    global_feature_importances,
)
from ml_service.models.anomaly import AnomalyModelArtifact
from ml_service.models.classifier import ClassifierModelArtifact
from ml_service.training.preprocessing import Preprocessor

TENANT = uuid.uuid4()
MACHINE = uuid.uuid4()


def _sample(feature_values: dict, label: FailureLabel = FailureLabel.NORMAL) -> DatasetSample:
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
        missing_features=(),
        quality_summary={},
        label=label,
        source_scenario_type=None,
        ground_truth_severity=0.0,
        split=SplitName.TRAIN,
    )


def test_global_feature_importances_uses_tree_attribute() -> None:
    class Fake:
        feature_importances_ = np.array([0.1, 0.7, 0.2])

    result = global_feature_importances(Fake(), ["a", "b", "c"], top_k=2)
    assert result[0].feature == "b"


def test_explain_classification_prediction_returns_no_causal_language_fields() -> None:
    train = [
        _sample({"pressure.current": 5.0, "flow.current": 20.0}, FailureLabel.NORMAL)
        for _ in range(10)
    ] + [
        _sample({"pressure.current": 20.0, "flow.current": 2.0}, FailureLabel.RESTRICTION)
        for _ in range(10)
    ]
    pre = Preprocessor(
        numeric_features=("pressure.current", "flow.current"), categorical_features=()
    )
    pre.fit(train)
    x = pre.transform(train)
    y = [s.label.value for s in train]
    estimator = LogisticRegression().fit(x, y)

    artifact = ClassifierModelArtifact(
        estimator=estimator,
        preprocessor=pre,
        feature_names=("pressure.current", "flow.current"),
        categorical_features=(),
        minimum_required_features=("pressure.current",),
        class_order=tuple(estimator.classes_),
    )
    probs = artifact.predict_proba([train[-1]])[0]
    predicted_idx = int(np.argmax(probs))
    contributions = explain_classification_prediction(artifact, x[-1], predicted_idx, top_k=3)
    assert all(hasattr(c, "feature") and hasattr(c, "magnitude") for c in contributions)
    for c in contributions:
        assert "cause" not in c.to_dict()


def test_explain_anomaly_prediction_ranks_by_z_score() -> None:
    train = [_sample({"pressure.current": v}) for v in (5.0, 5.1, 4.9, 5.0, 5.2)]
    pre = Preprocessor(numeric_features=("pressure.current",), categorical_features=())
    pre.fit(train)
    x = pre.transform(train)
    estimator = IsolationForest(n_estimators=20, random_state=1).fit(x)
    artifact = AnomalyModelArtifact(
        estimator=estimator,
        preprocessor=pre,
        numeric_features=("pressure.current",),
        minimum_required_features=("pressure.current",),
        threshold=0.0,
    )
    contributions = explain_anomaly_prediction(artifact, {"pressure.current": 50.0}, top_k=1)
    assert contributions[0].feature == "pressure.current"
    assert abs(contributions[0].magnitude) > 1.0
