"""Supervised classifier wrapper — baseline (logistic regression) and primary
(HistGradientBoostingClassifier) share this contract (Phase 11 brief §15-§18)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from ml_service.domain.labels import FailureLabel
from ml_service.training.preprocessing import HasFeatureValues, Preprocessor


class SklearnClassifier(Protocol):
    classes_: np.ndarray

    def predict_proba(self, x: np.ndarray) -> np.ndarray: ...
    def fit(
        self, x: np.ndarray, y: np.ndarray, sample_weight: np.ndarray | None = None
    ) -> object: ...


@dataclass
class ClassifierModelArtifact:
    estimator: SklearnClassifier
    preprocessor: Preprocessor
    feature_names: tuple[str, ...]
    categorical_features: tuple[str, ...]
    minimum_required_features: tuple[str, ...]
    class_order: tuple[str, ...]
    unknown_confidence_threshold: float = 0.4

    def predict_proba(self, samples: Sequence[HasFeatureValues]) -> np.ndarray:
        x = self.preprocessor.transform(samples)
        return self.estimator.predict_proba(x)

    def has_minimum_features(self, sample: HasFeatureValues) -> bool:
        missing = self.preprocessor.missing_feature_count(sample, self.minimum_required_features)
        return missing == 0

    def predict_label(self, probabilities: np.ndarray) -> tuple[FailureLabel, float]:
        """Returns `(predicted_label, max_probability)`. If the top probability is below
        `unknown_confidence_threshold`, the predicted label is forced to `UNKNOWN`
        (Phase 11 brief §11, §54) rather than a low-confidence guess among the known
        classes."""
        idx = int(np.argmax(probabilities))
        max_prob = float(probabilities[idx])
        if max_prob < self.unknown_confidence_threshold:
            return FailureLabel.UNKNOWN, max_prob
        return FailureLabel(self.class_order[idx]), max_prob
