"""On-demand ML inference orchestration (Phase 11 brief §39-§42), mirroring
`app.features.services.feature_engine`'s "latest" pattern: compute the current Phase 10
feature vector, run it through `ml-service`'s `InferenceService` against an explicit
VALIDATED-or-later model version (never "latest file in folder"), and persist the result.

This is the ONLY place backend code calls into `ml_service` — model logic itself
(preprocessing, scoring, explainability) never lives here or in an API route handler
(TECHNICAL_DECISIONS.md ADR-011).

If `ml-service` has no VALIDATED model registered yet, or the registered model raises, this
raises `MLModelNotAvailableError` rather than crashing the request — ML failure must never
break the rest of the platform (Phase 11 brief §41; see also LOOP.md "Failure Handling").
"""

from __future__ import annotations

import uuid

from ml_service.domain.feature_snapshot import FeatureSnapshot
from ml_service.domain.model_metadata import ModelLifecycleState
from ml_service.inference.service import InferenceService, ModelNotServableError
from ml_service.registry.registry import ModelNotFoundError, ModelRegistry
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import MLConfidenceCategory, MLInferenceStatus, MLResultKind
from app.domain.models import MLInferenceResult
from app.features.config.policy import FeaturePolicy
from app.features.services.feature_engine import FeatureEngine, FeatureMachineNotFoundError
from app.ml.registry import get_model_registry
from app.ml.repositories.ml_repository import MLInferenceResultRepository

_SERVABLE_STATUSES = (
    ModelLifecycleState.VALIDATED,
    ModelLifecycleState.STAGING,
    ModelLifecycleState.PRODUCTION,
)

_MODEL_FEATURE_SETS = {
    "LUBRICATION_ANOMALY_V1": "LUBRICATION_ANOMALY_V1",
    "FAILURE_CLASSIFICATION_V1": "FAILURE_CLASSIFICATION_V1",
}

_MODEL_RESULT_KIND = {
    "LUBRICATION_ANOMALY_V1": MLResultKind.ANOMALY,
    "FAILURE_CLASSIFICATION_V1": MLResultKind.CLASSIFICATION,
}


class MLMachineNotFoundError(LookupError):
    pass


class MLModelNotAvailableError(RuntimeError):
    pass


def _feature_result_to_snapshot(computed: object) -> FeatureSnapshot:
    return FeatureSnapshot(
        feature_vector_id=computed.feature_vector_id,  # type: ignore[attr-defined]
        as_of_timestamp=computed.as_of_timestamp,  # type: ignore[attr-defined]
        feature_set=computed.feature_set,  # type: ignore[attr-defined]
        feature_set_version=computed.feature_set_version,  # type: ignore[attr-defined]
        feature_values=dict(computed.feature_values),  # type: ignore[attr-defined]
        missing_features=tuple(computed.missing_features),  # type: ignore[attr-defined]
        quality_summary=dict(computed.quality_summary),  # type: ignore[attr-defined]
    )


class MLInferenceOrchestrationService:
    def __init__(
        self,
        session: AsyncSession,
        feature_policy: FeaturePolicy,
        registry: ModelRegistry | None = None,
    ) -> None:
        self._session = session
        self._feature_engine = FeatureEngine(session, feature_policy)
        self._repo = MLInferenceResultRepository(session)
        self._registry = registry or get_model_registry()
        self._inference_service = InferenceService(self._registry)

    async def compute_and_persist_latest(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID, model_id: str
    ) -> MLInferenceResult:
        feature_set = _MODEL_FEATURE_SETS.get(model_id)
        if feature_set is None:
            raise MLModelNotAvailableError(f"unknown model_id {model_id!r}")

        try:
            computed = await self._feature_engine.compute_latest(tenant_id, machine_id, feature_set)
        except FeatureMachineNotFoundError as exc:
            raise MLMachineNotFoundError(str(machine_id)) from exc

        entry = self._registry.latest_by_status(model_id, _SERVABLE_STATUSES)
        if entry is None:
            raise MLModelNotAvailableError(
                f"no VALIDATED (or later) version registered for {model_id}"
            )

        snapshot = _feature_result_to_snapshot(computed)
        try:
            if _MODEL_RESULT_KIND[model_id] == MLResultKind.ANOMALY:
                inference = self._inference_service.infer_anomaly(
                    snapshot, model_id, entry.model_version
                )
                orm = MLInferenceResult(
                    tenant_id=tenant_id,
                    machine_id=machine_id,
                    feature_vector_id=inference.feature_vector_id,
                    model_id=inference.model_id,
                    model_version=inference.model_version,
                    result_kind=MLResultKind.ANOMALY,
                    status=MLInferenceStatus(inference.status.value),
                    as_of_timestamp=inference.as_of_timestamp,
                    anomaly_score=inference.anomaly_score,
                    anomalous=inference.anomalous,
                    threshold=inference.threshold,
                    features_used=list(inference.features_used),
                    missing_features=list(inference.missing_features),
                    quality_summary=dict(inference.quality_summary),
                    explanation=dict(inference.explanation),
                )
            else:
                classification = self._inference_service.infer_classification(
                    snapshot, model_id, entry.model_version
                )
                orm = MLInferenceResult(
                    tenant_id=tenant_id,
                    machine_id=machine_id,
                    feature_vector_id=classification.feature_vector_id,
                    model_id=classification.model_id,
                    model_version=classification.model_version,
                    result_kind=MLResultKind.CLASSIFICATION,
                    status=MLInferenceStatus(classification.status.value),
                    as_of_timestamp=classification.as_of_timestamp,
                    predicted_class=classification.predicted_class,
                    class_probabilities=dict(classification.class_probabilities),
                    confidence_category=(
                        MLConfidenceCategory(classification.confidence_category.value)
                        if classification.confidence_category
                        else None
                    ),
                    features_used=list(classification.features_used),
                    missing_features=list(classification.missing_features),
                    quality_summary=dict(classification.quality_summary),
                    explanation=dict(classification.explanation),
                )
        except (ModelNotFoundError, ModelNotServableError) as exc:
            raise MLModelNotAvailableError(str(exc)) from exc

        await self._repo.insert(orm)
        await self._session.commit()
        return orm
