"""Evaluation metrics (Phase 11 brief §14, §27-§30). Accuracy alone is never reported as
sufficient; classification is always per-class precision/recall/F1 plus confusion matrix
plus PR-oriented metrics. Anomaly evaluation always includes detection-rate-by-scenario and
warning lead time, not only ROC-AUC.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)


@dataclass(frozen=True, slots=True)
class ClassificationReport:
    labels: tuple[str, ...]
    precision: dict[str, float]
    recall: dict[str, float]
    f1: dict[str, float]
    support: dict[str, int]
    macro_f1: float
    weighted_f1: float
    confusion_matrix: list[list[int]]
    pr_auc_one_vs_rest: dict[str, float]

    def to_dict(self) -> dict[str, object]:
        return {
            "labels": list(self.labels),
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "support": self.support,
            "macro_f1": self.macro_f1,
            "weighted_f1": self.weighted_f1,
            "confusion_matrix": self.confusion_matrix,
            "pr_auc_one_vs_rest": self.pr_auc_one_vs_rest,
        }


def classification_report(
    y_true: list[str],
    y_pred: list[str],
    y_proba: np.ndarray,
    class_order: tuple[str, ...],
) -> ClassificationReport:
    labels = sorted(set(y_true) | set(y_pred) | set(class_order))
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0
    )
    macro_f1 = float(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0))
    weighted_f1 = float(
        f1_score(y_true, y_pred, labels=labels, average="weighted", zero_division=0)
    )
    cm = confusion_matrix(y_true, y_pred, labels=labels)

    pr_auc: dict[str, float] = {}
    for i, label in enumerate(class_order):
        y_true_binary = np.array([1 if t == label else 0 for t in y_true])
        if y_true_binary.sum() == 0 or i >= y_proba.shape[1]:
            continue
        pr_auc[label] = float(average_precision_score(y_true_binary, y_proba[:, i]))

    return ClassificationReport(
        labels=tuple(labels),
        precision=dict(zip(labels, (float(p) for p in precision), strict=True)),
        recall=dict(zip(labels, (float(r) for r in recall), strict=True)),
        f1=dict(zip(labels, (float(f) for f in f1), strict=True)),
        support=dict(zip(labels, (int(s) for s in support), strict=True)),
        macro_f1=macro_f1,
        weighted_f1=weighted_f1,
        confusion_matrix=cm.tolist(),
        pr_auc_one_vs_rest=pr_auc,
    )


def false_positive_rate(y_true_normal: np.ndarray, y_pred_anomalous: np.ndarray) -> float:
    """`y_true_normal` is True where ground truth is NORMAL; FPR = fraction of those flagged
    anomalous."""
    normal_mask = y_true_normal
    if normal_mask.sum() == 0:
        return 0.0
    return float(y_pred_anomalous[normal_mask].sum() / normal_mask.sum())


def n_of_m_persistence(flags: list[bool], n: int, m: int) -> list[bool]:
    """A tick counts as a "persistent" detection only if at least `n` of the last `m` ticks
    (inclusive) were flagged — evaluation-only detection smoothing (Phase 11 brief §30),
    never a production alert debounce."""
    persistent = []
    for i in range(len(flags)):
        window = flags[max(0, i - m + 1) : i + 1]
        persistent.append(sum(window) >= n)
    return persistent


@dataclass(frozen=True, slots=True)
class WarningLeadTime:
    first_detection_at: datetime | None
    first_persistent_detection_at: datetime | None
    severe_onset_at: datetime | None
    lead_time_seconds: float | None


def warning_lead_time(
    timestamps: list[datetime],
    flags: list[bool],
    severities: list[float],
    *,
    persistence_n: int = 3,
    persistence_m: int = 5,
    severe_severity_threshold: float = 0.6,
) -> WarningLeadTime:
    """Time from the first PERSISTENT model detection to the first tick ground truth calls
    SEVERE (severity >= `severe_severity_threshold`). Ground truth is consulted only to
    measure lead time AFTER the fact — never exposed to the model as a feature (Phase 11
    brief §29)."""
    if not timestamps:
        return WarningLeadTime(None, None, None, None)

    persistent_flags = n_of_m_persistence(flags, persistence_n, persistence_m)

    first_detection_at = next((t for t, f in zip(timestamps, flags, strict=True) if f), None)
    first_persistent_at = next(
        (t for t, f in zip(timestamps, persistent_flags, strict=True) if f), None
    )
    severe_onset_at = next(
        (t for t, s in zip(timestamps, severities, strict=True) if s >= severe_severity_threshold),
        None,
    )

    lead_time: float | None = None
    if first_persistent_at is not None and severe_onset_at is not None:
        lead_time = (severe_onset_at - first_persistent_at).total_seconds()

    return WarningLeadTime(
        first_detection_at=first_detection_at,
        first_persistent_detection_at=first_persistent_at,
        severe_onset_at=severe_onset_at,
        lead_time_seconds=lead_time,
    )
