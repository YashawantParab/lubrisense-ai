"""Explainability (Phase 11 brief §37-§38).

Language rule enforced structurally, not just by convention: every function here returns
"features contributing most to this prediction" style structured data — feature name plus a
magnitude/direction — never a causal sentence. Callers (inference service, API, frontend)
must not synthesize causal language ("this feature caused...") from this output.

Tree-model per-prediction attribution uses feature ablation (zero out one active feature at
a time, measure the resulting probability shift) rather than SHAP — a deliberate dependency
choice (`docs/ML_ARCHITECTURE.md` "Explainability"): avoids adding a heavyweight SHAP
dependency to a CPU-only demo-scale service for marginal benefit over an ablation heuristic
at this dataset size. Isolation Forest attribution uses a train-distribution z-score
heuristic (§37 "a safe heuristic if exact attribution is unavailable") since Isolation
Forest has no native per-sample feature attribution.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from ml_service.models.anomaly import AnomalyModelArtifact
from ml_service.models.classifier import ClassifierModelArtifact


@dataclass(frozen=True, slots=True)
class FeatureContribution:
    feature: str
    magnitude: float

    def to_dict(self) -> dict[str, object]:
        return {"feature": self.feature, "magnitude": round(self.magnitude, 6)}


def global_feature_importances(
    estimator: object, feature_names: list[str], top_k: int = 15
) -> list[FeatureContribution]:
    importances = getattr(estimator, "feature_importances_", None)
    if importances is None:
        return []
    ranked = sorted(zip(feature_names, importances, strict=True), key=lambda pair: -abs(pair[1]))
    return [FeatureContribution(name, float(value)) for name, value in ranked[:top_k]]


def explain_classification_prediction(
    artifact: ClassifierModelArtifact,
    x_row: np.ndarray,
    predicted_class_index: int,
    top_k: int = 5,
) -> list[FeatureContribution]:
    """Feature-ablation attribution for one prediction: 'features contributing most to this
    prediction', not a causal claim."""
    baseline = artifact.estimator.predict_proba(x_row.reshape(1, -1))[0, predicted_class_index]
    contributions: list[FeatureContribution] = []
    for i, column_name in enumerate(artifact.preprocessor.output_columns):
        if x_row[i] == 0:
            continue
        ablated = x_row.copy()
        ablated[i] = 0.0
        ablated_prob = artifact.estimator.predict_proba(ablated.reshape(1, -1))[
            0, predicted_class_index
        ]
        contributions.append(FeatureContribution(column_name, float(baseline - ablated_prob)))
    contributions.sort(key=lambda c: -abs(c.magnitude))
    return contributions[:top_k]


def explain_anomaly_prediction(
    artifact: AnomalyModelArtifact, feature_values: Mapping[str, object], top_k: int = 5
) -> list[FeatureContribution]:
    """Safe heuristic (Phase 11 brief §37): rank features by |z-score| against the TRAIN
    distribution the preprocessor was fit on. A large deviation from typical healthy
    behavior is reported as a top contributor — not a claim of exact model attribution,
    which Isolation Forest does not natively provide."""
    contributions: list[FeatureContribution] = []
    for name in artifact.numeric_features:
        value = feature_values.get(name)
        if value is None:
            continue
        std = artifact.preprocessor.stddevs.get(name, 0.0)
        mean = artifact.preprocessor.means.get(name, 0.0)
        if std <= 1e-9:
            continue
        numeric_value = 1.0 if isinstance(value, bool) else float(value)  # type: ignore[arg-type]
        z_score = (numeric_value - mean) / std
        contributions.append(FeatureContribution(name, float(z_score)))
    contributions.sort(key=lambda c: -abs(c.magnitude))
    return contributions[:top_k]
