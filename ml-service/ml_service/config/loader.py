"""Versioned model configs (Phase 11 brief §68): features, hyperparameters, thresholds,
minimum features, seed, dataset requirements — all in one reviewable YAML file per model,
never hardcoded inside a training script.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AnomalyConfig(_Frozen):
    model_id: str
    model_version: str
    feature_set: str
    feature_set_version: str
    seed: int
    n_estimators: int
    contamination: float
    target_validation_fpr: float
    minimum_required_features: tuple[str, ...]
    persistence_n: int
    persistence_m: int
    severe_severity_threshold: float


class BaselineClassifierConfig(_Frozen):
    seed: int
    class_weight: str
    max_iter: int


class PrimaryClassifierConfig(_Frozen):
    seed: int
    max_iter: int
    max_depth: int
    learning_rate: float
    l2_regularization: float


class ClassifierConfig(_Frozen):
    model_id: str
    model_version: str
    feature_set: str
    feature_set_version: str
    seed: int
    minimum_required_features: tuple[str, ...]
    unknown_confidence_threshold: float
    confidence_moderate_threshold: float
    confidence_high_threshold: float
    baseline: BaselineClassifierConfig
    primary: PrimaryClassifierConfig


def load_anomaly_config(path: Path | None = None) -> AnomalyConfig:
    raw = yaml.safe_load((path or CONFIG_DIR / "anomaly_v1.yaml").read_text())
    return AnomalyConfig.model_validate(raw)


def load_classifier_config(path: Path | None = None) -> ClassifierConfig:
    raw = yaml.safe_load((path or CONFIG_DIR / "classifier_v1.yaml").read_text())
    return ClassifierConfig.model_validate(raw)
