from datetime import UTC, datetime, timedelta

import numpy as np

from ml_service.evaluation.metrics import (
    classification_report,
    false_positive_rate,
    n_of_m_persistence,
    warning_lead_time,
)


def test_n_of_m_persistence_requires_sustained_flags() -> None:
    flags = [True, False, False, False, False]
    persistent = n_of_m_persistence(flags, n=3, m=5)
    assert persistent == [False] * 5

    flags2 = [True, True, True, True, True]
    persistent2 = n_of_m_persistence(flags2, n=3, m=5)
    assert persistent2[2] is True  # by the 3rd consecutive True, window has 3 Trues


def test_false_positive_rate_only_counts_normal_ground_truth() -> None:
    y_true_normal = np.array([True, True, False, False])
    y_pred_anomalous = np.array([True, False, True, True])
    fpr = false_positive_rate(y_true_normal, y_pred_anomalous)
    assert fpr == 0.5  # 1 of 2 NORMAL samples flagged


def test_warning_lead_time_uses_first_persistent_not_first_isolated_detection() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    timestamps = [base + timedelta(minutes=i) for i in range(10)]
    # isolated blip at t=1, then sustained anomaly from t=5
    flags = [False, True, False, False, False, True, True, True, True, True]
    severities = [0.0, 0.0, 0.0, 0.0, 0.0, 0.3, 0.4, 0.5, 0.65, 0.8]

    result = warning_lead_time(
        timestamps,
        flags,
        severities,
        persistence_n=3,
        persistence_m=5,
        severe_severity_threshold=0.6,
    )
    assert result.first_detection_at == timestamps[1]
    assert result.first_persistent_detection_at is not None
    assert result.first_persistent_detection_at >= timestamps[5]
    assert result.severe_onset_at == timestamps[8]
    assert result.lead_time_seconds is not None
    assert result.lead_time_seconds > 0


def test_classification_report_reports_per_class_not_only_accuracy() -> None:
    y_true = ["NORMAL", "NORMAL", "RESTRICTION", "RESTRICTION"]
    y_pred = ["NORMAL", "RESTRICTION", "RESTRICTION", "RESTRICTION"]
    class_order = ("NORMAL", "RESTRICTION")
    y_proba = np.array([[0.9, 0.1], [0.4, 0.6], [0.2, 0.8], [0.1, 0.9]])

    report = classification_report(y_true, y_pred, y_proba, class_order)
    assert "NORMAL" in report.precision
    assert "RESTRICTION" in report.recall
    assert report.confusion_matrix
    assert 0.0 <= report.macro_f1 <= 1.0
