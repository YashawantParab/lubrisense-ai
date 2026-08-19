"""Model artifact/version/lifecycle contracts (Phase 11 brief §23-§25)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class ModelType(StrEnum):
    ANOMALY_ISOLATION_FOREST = "ANOMALY_ISOLATION_FOREST"
    CLASSIFIER_BASELINE_LOGISTIC_REGRESSION = "CLASSIFIER_BASELINE_LOGISTIC_REGRESSION"
    CLASSIFIER_PRIMARY_HIST_GRADIENT_BOOSTING = "CLASSIFIER_PRIMARY_HIST_GRADIENT_BOOSTING"


class ModelLifecycleState(StrEnum):
    """Phase 11 brief §25 — Phase 11 never auto-promotes past `VALIDATED`."""

    EXPERIMENT = "EXPERIMENT"
    VALIDATED = "VALIDATED"
    STAGING = "STAGING"
    PRODUCTION = "PRODUCTION"
    RETIRED = "RETIRED"


@dataclass(frozen=True, slots=True)
class ModelMetadata:
    model_id: str
    model_version: str
    model_type: ModelType
    training_time: datetime
    dataset_id: str
    dataset_version: str
    feature_set: str
    feature_set_version: str
    features: tuple[str, ...]
    hyperparameters: dict[str, object]
    metrics: dict[str, object]
    thresholds: dict[str, float]
    seed: int
    code_version: str
    status: ModelLifecycleState
    limitations: tuple[str, ...]
    minimum_required_features: tuple[str, ...] = field(default_factory=tuple)
    artifact_path: str = ""
    preprocessor_path: str = ""
    artifact_checksum: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "model_type": self.model_type.value,
            "training_time": self.training_time.isoformat(),
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "feature_set": self.feature_set,
            "feature_set_version": self.feature_set_version,
            "features": list(self.features),
            "hyperparameters": self.hyperparameters,
            "metrics": self.metrics,
            "thresholds": self.thresholds,
            "seed": self.seed,
            "code_version": self.code_version,
            "status": self.status.value,
            "limitations": list(self.limitations),
            "minimum_required_features": list(self.minimum_required_features),
            "artifact_path": self.artifact_path,
            "preprocessor_path": self.preprocessor_path,
            "artifact_checksum": self.artifact_checksum,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ModelMetadata:
        return ModelMetadata(
            model_id=str(data["model_id"]),
            model_version=str(data["model_version"]),
            model_type=ModelType(data["model_type"]),
            training_time=datetime.fromisoformat(str(data["training_time"])),
            dataset_id=str(data["dataset_id"]),
            dataset_version=str(data["dataset_version"]),
            feature_set=str(data["feature_set"]),
            feature_set_version=str(data["feature_set_version"]),
            features=tuple(data["features"]),
            hyperparameters=dict(data["hyperparameters"]),
            metrics=dict(data["metrics"]),
            thresholds=dict(data["thresholds"]),
            seed=int(data["seed"]),
            code_version=str(data["code_version"]),
            status=ModelLifecycleState(data["status"]),
            limitations=tuple(data["limitations"]),
            minimum_required_features=tuple(data.get("minimum_required_features", ())),
            artifact_path=str(data.get("artifact_path", "")),
            preprocessor_path=str(data.get("preprocessor_path", "")),
            artifact_checksum=str(data.get("artifact_checksum", "")),
        )
