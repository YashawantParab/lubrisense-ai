"""Phase 11 ML API contracts. `ml` output is evidence, never a diagnosis/decision — see
`docs/ML_ARCHITECTURE.md` "Core principle"."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MLInferenceResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    machine_id: uuid.UUID
    feature_vector_id: uuid.UUID
    model_id: str
    model_version: str
    result_kind: str
    status: str
    as_of_timestamp: datetime
    anomaly_score: float | None
    anomalous: bool | None
    threshold: float | None
    predicted_class: str | None
    class_probabilities: dict[str, float]
    confidence_category: str | None
    features_used: list[str]
    missing_features: list[str]
    quality_summary: dict[str, object]
    explanation: dict[str, object]
    created_at: datetime


class ModelSummaryResponse(BaseModel):
    model_id: str
    model_version: str
    model_type: str
    status: str
    training_time: datetime
    dataset_id: str
    dataset_version: str
    feature_set: str
    feature_set_version: str


class ModelDetailResponse(ModelSummaryResponse):
    features: list[str]
    hyperparameters: dict[str, object]
    metrics: dict[str, object]
    thresholds: dict[str, float]
    seed: int
    code_version: str
    limitations: list[str]
    minimum_required_features: list[str]
