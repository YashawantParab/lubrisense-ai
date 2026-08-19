"""Inference service (Phase 11 brief §39-§41). Loads an explicit, validated model version
through the registry (never "latest file in folder"), applies the minimum-feature check
before ever calling a model, and returns the structured contracts from
`ml_service.domain.inference`. Anomaly output is never called "failure"; classifier
probabilities are model probabilities, never "truth" — see the module-level contract types.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ml_service.domain.feature_snapshot import FeatureSnapshot
from ml_service.domain.inference import (
    AnomalyInferenceResult,
    ClassificationInferenceResult,
    ConfidenceCategory,
    InferenceStatus,
)
from ml_service.domain.labels import FailureLabel
from ml_service.domain.model_metadata import ModelLifecycleState
from ml_service.explainability.explain import (
    explain_anomaly_prediction,
    explain_classification_prediction,
)
from ml_service.models.anomaly import AnomalyModelArtifact
from ml_service.models.classifier import ClassifierModelArtifact
from ml_service.registry.registry import ModelRegistry

_SERVABLE_STATUSES = (
    ModelLifecycleState.VALIDATED,
    ModelLifecycleState.STAGING,
    ModelLifecycleState.PRODUCTION,
)


class ModelNotServableError(RuntimeError):
    pass


def _confidence_category(probability: float, thresholds: dict[str, float]) -> ConfidenceCategory:
    high = thresholds.get("high", 0.75)
    moderate = thresholds.get("moderate", 0.5)
    if probability >= high:
        return ConfidenceCategory.HIGH
    if probability >= moderate:
        return ConfidenceCategory.MODERATE
    return ConfidenceCategory.LOW


class InferenceService:
    def __init__(self, registry: ModelRegistry | None = None) -> None:
        self._registry = registry or ModelRegistry()

    def infer_anomaly(
        self, snapshot: FeatureSnapshot, model_id: str, model_version: str
    ) -> AnomalyInferenceResult:
        artifact, metadata = self._registry.load(model_id, model_version)
        if metadata.status not in _SERVABLE_STATUSES:
            raise ModelNotServableError(
                f"{model_id}@{model_version} is {metadata.status.value}, not servable"
            )
        assert isinstance(artifact, AnomalyModelArtifact)

        now = datetime.now(UTC)
        missing_required = [
            name
            for name in artifact.minimum_required_features
            if snapshot.feature_values.get(name) is None
        ]
        if missing_required:
            return AnomalyInferenceResult(
                model_id=model_id,
                model_version=model_version,
                feature_vector_id=snapshot.feature_vector_id,
                as_of_timestamp=snapshot.as_of_timestamp,
                status=InferenceStatus.INSUFFICIENT_FEATURES,
                anomaly_score=None,
                anomalous=None,
                threshold=artifact.threshold,
                features_used=(),
                missing_features=tuple(missing_required),
                quality_summary=snapshot.quality_summary,
                explanation={"reason": "minimum required features unavailable"},
                created_at=now,
            )

        score = float(artifact.anomaly_scores([snapshot])[0])
        anomalous = bool(score >= artifact.threshold)
        contributions = explain_anomaly_prediction(artifact, snapshot.feature_values)
        return AnomalyInferenceResult(
            model_id=model_id,
            model_version=model_version,
            feature_vector_id=snapshot.feature_vector_id,
            as_of_timestamp=snapshot.as_of_timestamp,
            status=InferenceStatus.OK,
            anomaly_score=score,
            anomalous=anomalous,
            threshold=artifact.threshold,
            features_used=artifact.numeric_features,
            missing_features=snapshot.missing_features,
            quality_summary=snapshot.quality_summary,
            explanation={
                "top_contributing_features": [c.to_dict() for c in contributions],
                "note": (
                    "features contributing most to this anomaly score relative to healthy "
                    "training behavior, not a diagnosis"
                ),
            },
            created_at=now,
        )

    def infer_classification(
        self, snapshot: FeatureSnapshot, model_id: str, model_version: str
    ) -> ClassificationInferenceResult:
        artifact, metadata = self._registry.load(model_id, model_version)
        if metadata.status not in _SERVABLE_STATUSES:
            raise ModelNotServableError(
                f"{model_id}@{model_version} is {metadata.status.value}, not servable"
            )
        assert isinstance(artifact, ClassifierModelArtifact)

        now = datetime.now(UTC)
        missing_required = [
            name
            for name in artifact.minimum_required_features
            if snapshot.feature_values.get(name) is None
        ]
        if missing_required:
            return ClassificationInferenceResult(
                model_id=model_id,
                model_version=model_version,
                feature_vector_id=snapshot.feature_vector_id,
                as_of_timestamp=snapshot.as_of_timestamp,
                status=InferenceStatus.INSUFFICIENT_FEATURES,
                predicted_class=None,
                class_probabilities={},
                confidence_category=None,
                features_used=(),
                missing_features=tuple(missing_required),
                quality_summary=snapshot.quality_summary,
                explanation={"reason": "minimum required features unavailable"},
                created_at=now,
                reason="INSUFFICIENT_FEATURES: required evidence missing at this timestamp",
            )

        probabilities = artifact.predict_proba([snapshot])[0]
        predicted_label, max_prob = artifact.predict_label(probabilities)
        class_probabilities = dict(
            zip(artifact.class_order, (float(p) for p in probabilities), strict=True)
        )

        status = (
            InferenceStatus.UNKNOWN
            if predicted_label == FailureLabel.UNKNOWN
            else InferenceStatus.OK
        )
        confidence = _confidence_category(max_prob, metadata.thresholds)

        explanation: dict[str, object] = {
            "note": "features contributing most to this prediction, not a causal explanation",
        }
        if status == InferenceStatus.OK:
            x = artifact.preprocessor.transform([snapshot])[0]
            predicted_index = artifact.class_order.index(predicted_label.value)
            contributions = explain_classification_prediction(artifact, x, predicted_index)
            explanation["top_contributing_features"] = [c.to_dict() for c in contributions]

        return ClassificationInferenceResult(
            model_id=model_id,
            model_version=model_version,
            feature_vector_id=snapshot.feature_vector_id,
            as_of_timestamp=snapshot.as_of_timestamp,
            status=status,
            predicted_class=predicted_label.value,
            class_probabilities=class_probabilities,
            confidence_category=confidence,
            features_used=artifact.feature_names,
            missing_features=snapshot.missing_features,
            quality_summary=snapshot.quality_summary,
            explanation=explanation,
            created_at=now,
            reason=(
                "below confidence threshold for a known class"
                if status == InferenceStatus.UNKNOWN
                else None
            ),
        )
