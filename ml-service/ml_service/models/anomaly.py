"""Isolation Forest anomaly model wrapper (Phase 11 brief §12-§14)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import IsolationForest

from ml_service.training.preprocessing import HasFeatureValues, Preprocessor


@dataclass
class AnomalyModelArtifact:
    estimator: IsolationForest
    preprocessor: Preprocessor
    numeric_features: tuple[str, ...]
    minimum_required_features: tuple[str, ...]
    threshold: float = 0.0

    def anomaly_scores(self, samples: Sequence[HasFeatureValues]) -> np.ndarray:
        """Higher = more anomalous (sklearn's own `score_samples` convention is inverted:
        lower = more anomalous), so this is `-score_samples(X)` for readability everywhere
        else in this codebase."""
        x = self.preprocessor.transform(samples)
        return np.asarray(-self.estimator.score_samples(x), dtype=np.float64)

    def is_anomalous(self, scores: np.ndarray) -> np.ndarray:
        return scores >= self.threshold

    def has_minimum_features(self, sample: HasFeatureValues) -> bool:
        missing = self.preprocessor.missing_feature_count(sample, self.minimum_required_features)
        return missing == 0


def fit_isolation_forest(
    train_normal_samples: Sequence[HasFeatureValues],
    preprocessor: Preprocessor,
    *,
    n_estimators: int,
    contamination: float,
    seed: int,
) -> IsolationForest:
    x = preprocessor.transform(train_normal_samples)
    estimator = IsolationForest(
        n_estimators=n_estimators,
        contamination=contamination,
        random_state=seed,
        n_jobs=-1,
    )
    estimator.fit(x)
    return estimator
