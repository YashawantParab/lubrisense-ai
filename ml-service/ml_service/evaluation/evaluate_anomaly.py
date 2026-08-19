"""Anomaly-model evaluation (Phase 11 brief §14, §29-§30, §56-§62). Judged on more than
ROC-AUC: precision/recall/F1 for the binary "anomalous vs NORMAL" view, PR-AUC, false
positive rate on trusted healthy data, per-scenario detection rate, and warning lead time.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np
from sklearn.metrics import average_precision_score, precision_recall_fscore_support

from ml_service.domain.dataset import DatasetSample
from ml_service.domain.labels import FailureLabel
from ml_service.evaluation.metrics import WarningLeadTime, false_positive_rate, warning_lead_time
from ml_service.models.anomaly import AnomalyModelArtifact


@dataclass(frozen=True, slots=True)
class AnomalyEvaluationResult:
    sample_count: int
    healthy_false_positive_rate: float
    binary_precision: float
    binary_recall: float
    binary_f1: float
    pr_auc: float
    detection_rate_by_scenario: dict[str, float]
    warning_lead_time_by_run: dict[str, float | None]
    top_deviating_features: list[tuple[str, float]]

    def to_dict(self) -> dict[str, object]:
        return {
            "sample_count": self.sample_count,
            "healthy_false_positive_rate": self.healthy_false_positive_rate,
            "binary_precision": self.binary_precision,
            "binary_recall": self.binary_recall,
            "binary_f1": self.binary_f1,
            "pr_auc": self.pr_auc,
            "detection_rate_by_scenario": self.detection_rate_by_scenario,
            "warning_lead_time_by_run_seconds": self.warning_lead_time_by_run,
            "top_deviating_features": [
                {"feature": f, "avg_abs_z": z} for f, z in self.top_deviating_features
            ],
        }


def evaluate_anomaly_model(
    artifact: AnomalyModelArtifact,
    samples: list[DatasetSample],
    *,
    persistence_n: int,
    persistence_m: int,
    severe_severity_threshold: float,
) -> AnomalyEvaluationResult:
    if not samples:
        raise ValueError("no samples to evaluate")

    scores = artifact.anomaly_scores(samples)
    anomalous = artifact.is_anomalous(scores)
    y_true_normal = np.array([s.label == FailureLabel.NORMAL for s in samples])
    y_true_anomalous_binary = ~y_true_normal

    fpr = false_positive_rate(y_true_normal, anomalous)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true_anomalous_binary, anomalous, average="binary", zero_division=0
    )
    pr_auc = (
        float(average_precision_score(y_true_anomalous_binary, scores))
        if y_true_anomalous_binary.any()
        else float("nan")
    )

    by_scenario: dict[str, list[bool]] = defaultdict(list)
    for sample, flag in zip(samples, anomalous, strict=True):
        if sample.label == FailureLabel.NORMAL:
            continue
        key = sample.source_scenario_type or sample.label.value
        by_scenario[key].append(bool(flag))
    detection_rate_by_scenario = {
        key: (sum(flags) / len(flags) if flags else 0.0) for key, flags in by_scenario.items()
    }

    by_run: dict[str, list[tuple[DatasetSample, bool, float]]] = defaultdict(list)
    for sample, flag, score in zip(samples, anomalous, scores, strict=True):
        by_run[sample.run_id].append((sample, bool(flag), float(score)))

    lead_times: dict[str, float | None] = {}
    for run_id, rows in by_run.items():
        rows.sort(key=lambda r: r[0].as_of_timestamp)
        if all(r[0].label == FailureLabel.NORMAL for r in rows):
            continue
        timestamps = [r[0].as_of_timestamp for r in rows]
        flags = [r[1] for r in rows]
        severities = [r[0].ground_truth_severity for r in rows]
        result: WarningLeadTime = warning_lead_time(
            timestamps,
            flags,
            severities,
            persistence_n=persistence_n,
            persistence_m=persistence_m,
            severe_severity_threshold=severe_severity_threshold,
        )
        lead_times[run_id] = result.lead_time_seconds

    z_sums: dict[str, float] = defaultdict(float)
    z_counts: dict[str, int] = defaultdict(int)
    anomalous_samples = [s for s, flag in zip(samples, anomalous, strict=True) if flag]
    for sample in anomalous_samples[:200]:
        for name in artifact.numeric_features:
            value = sample.feature_values.get(name)
            if value is None:
                continue
            std = artifact.preprocessor.stddevs.get(name, 0.0)
            mean = artifact.preprocessor.means.get(name, 0.0)
            if std <= 1e-9:
                continue
            numeric = 1.0 if isinstance(value, bool) else float(value)
            z_sums[name] += abs((numeric - mean) / std)
            z_counts[name] += 1
    top_deviating = sorted(
        ((name, z_sums[name] / z_counts[name]) for name in z_sums if z_counts[name] > 0),
        key=lambda pair: -pair[1],
    )[:10]

    return AnomalyEvaluationResult(
        sample_count=len(samples),
        healthy_false_positive_rate=fpr,
        binary_precision=float(precision),
        binary_recall=float(recall),
        binary_f1=float(f1),
        pr_auc=pr_auc,
        detection_rate_by_scenario=detection_rate_by_scenario,
        warning_lead_time_by_run=lead_times,
        top_deviating_features=top_deviating,
    )
