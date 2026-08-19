"""Classifier evaluation (Phase 11 brief §27-§28, §51-§62). Never reports accuracy alone."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ml_service.domain.dataset import DatasetSample
from ml_service.evaluation.metrics import ClassificationReport, classification_report
from ml_service.models.classifier import ClassifierModelArtifact


@dataclass(frozen=True, slots=True)
class ClassifierEvaluationResult:
    sample_count: int
    report: ClassificationReport
    unknown_rate: float
    train_report: ClassificationReport | None
    validation_report: ClassificationReport | None

    def to_dict(self) -> dict[str, object]:
        return {
            "sample_count": self.sample_count,
            "test_report": self.report.to_dict(),
            "unknown_rate": self.unknown_rate,
            "train_report": self.train_report.to_dict() if self.train_report else None,
            "validation_report": self.validation_report.to_dict()
            if self.validation_report
            else None,
        }


def _predict_labels(
    artifact: ClassifierModelArtifact, samples: list[DatasetSample]
) -> tuple[list[str], np.ndarray]:
    probabilities = artifact.predict_proba(samples)
    predicted = []
    for row in probabilities:
        label, _ = artifact.predict_label(row)
        predicted.append(label.value)
    return predicted, probabilities


def evaluate_classifier(
    artifact: ClassifierModelArtifact,
    test_samples: list[DatasetSample],
    *,
    train_samples: list[DatasetSample] | None = None,
    validation_samples: list[DatasetSample] | None = None,
) -> ClassifierEvaluationResult:
    if not test_samples:
        raise ValueError("no test samples to evaluate")

    y_true = [s.label.value for s in test_samples]
    y_pred, y_proba = _predict_labels(artifact, test_samples)
    report = classification_report(y_true, y_pred, y_proba, artifact.class_order)
    unknown_rate = sum(1 for p in y_pred if p == "UNKNOWN") / len(y_pred)

    train_report = None
    if train_samples:
        yt_true = [s.label.value for s in train_samples]
        yt_pred, yt_proba = _predict_labels(artifact, train_samples)
        train_report = classification_report(yt_true, yt_pred, yt_proba, artifact.class_order)

    validation_report = None
    if validation_samples:
        yv_true = [s.label.value for s in validation_samples]
        yv_pred, yv_proba = _predict_labels(artifact, validation_samples)
        validation_report = classification_report(yv_true, yv_pred, yv_proba, artifact.class_order)

    return ClassifierEvaluationResult(
        sample_count=len(test_samples),
        report=report,
        unknown_rate=unknown_rate,
        train_report=train_report,
        validation_report=validation_report,
    )
