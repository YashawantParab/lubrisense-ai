"""Structured inference contracts (Phase 11 brief §35-§36). ML output here is EVIDENCE, not
a diagnosis or a decision — see `docs/ML_ARCHITECTURE.md` "Core principle." Anomaly output
is never called "failure"; classifier probabilities are model probabilities, never "truth."
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class ConfidenceCategory(StrEnum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


class InferenceStatus(StrEnum):
    OK = "OK"
    INSUFFICIENT_FEATURES = "INSUFFICIENT_FEATURES"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class AnomalyInferenceResult:
    model_id: str
    model_version: str
    feature_vector_id: uuid.UUID
    as_of_timestamp: datetime
    status: InferenceStatus
    anomaly_score: float | None
    anomalous: bool | None
    threshold: float
    features_used: tuple[str, ...]
    missing_features: tuple[str, ...]
    quality_summary: dict[str, object]
    explanation: dict[str, object]
    created_at: datetime

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "feature_vector_id": str(self.feature_vector_id),
            "as_of_timestamp": self.as_of_timestamp.isoformat(),
            "status": self.status.value,
            "anomaly_score": self.anomaly_score,
            "anomalous": self.anomalous,
            "threshold": self.threshold,
            "features_used": list(self.features_used),
            "missing_features": list(self.missing_features),
            "quality_summary": self.quality_summary,
            "explanation": self.explanation,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class ClassificationInferenceResult:
    model_id: str
    model_version: str
    feature_vector_id: uuid.UUID
    as_of_timestamp: datetime
    status: InferenceStatus
    predicted_class: str | None
    class_probabilities: dict[str, float]
    confidence_category: ConfidenceCategory | None
    features_used: tuple[str, ...]
    missing_features: tuple[str, ...]
    quality_summary: dict[str, object]
    explanation: dict[str, object]
    created_at: datetime
    reason: str | None = field(default=None)

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "feature_vector_id": str(self.feature_vector_id),
            "as_of_timestamp": self.as_of_timestamp.isoformat(),
            "status": self.status.value,
            "predicted_class": self.predicted_class,
            "class_probabilities": self.class_probabilities,
            "confidence_category": (
                self.confidence_category.value if self.confidence_category else None
            ),
            "features_used": list(self.features_used),
            "missing_features": list(self.missing_features),
            "quality_summary": self.quality_summary,
            "explanation": self.explanation,
            "created_at": self.created_at.isoformat(),
            "reason": self.reason,
        }
