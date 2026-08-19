"""Reproducible training command (Phase 11 brief §21):

    python -m ml_service.training.train_anomaly --dataset-dir data/datasets/PHASE11_REFERENCE

Fits an Isolation Forest on TRAIN's NORMAL-labeled samples, selects the operating threshold
on VALIDATION's NORMAL-labeled samples only (never TEST), evaluates on TEST, and registers
the resulting artifact + metadata through the model registry.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from ml_service import __code_version__
from ml_service.config.loader import load_anomaly_config
from ml_service.datasets.builder import DatasetBuilder
from ml_service.domain.dataset import SplitName
from ml_service.domain.labels import FailureLabel
from ml_service.domain.model_metadata import ModelLifecycleState, ModelMetadata, ModelType
from ml_service.evaluation.evaluate_anomaly import evaluate_anomaly_model
from ml_service.models.anomaly import AnomalyModelArtifact, fit_isolation_forest
from ml_service.registry.registry import ModelRegistry
from ml_service.training.feature_sets import ANOMALY_EXCLUDED_FEATURES, select_feature_names
from ml_service.training.preprocessing import Preprocessor

_DEFAULT_EVAL_PATH = (
    Path(__file__).resolve().parents[2] / "artifacts" / "evaluation" / "anomaly_evaluation.json"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Train the LUBRICATION_ANOMALY_V1 Isolation Forest."
    )
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--artifacts-dir", type=Path, default=None)
    parser.add_argument("--evaluation-out", type=Path, default=_DEFAULT_EVAL_PATH)
    args = parser.parse_args()

    config = load_anomaly_config(args.config)
    manifest, samples = DatasetBuilder.load(args.dataset_dir)

    train = [s for s in samples if s.split == SplitName.TRAIN]
    validation = [s for s in samples if s.split == SplitName.VALIDATION]
    test = [s for s in samples if s.split == SplitName.TEST]
    if not train or not validation or not test:
        raise SystemExit(
            f"dataset must have non-empty TRAIN/VALIDATION/TEST splits, got "
            f"{len(train)}/{len(validation)}/{len(test)}"
        )

    numeric_features = select_feature_names(manifest.feature_list, ANOMALY_EXCLUDED_FEATURES)

    preprocessor = Preprocessor(numeric_features=numeric_features, categorical_features=())
    preprocessor.fit(train)

    train_normal = [s for s in train if s.label == FailureLabel.NORMAL]
    if not train_normal:
        raise SystemExit("no NORMAL-labeled samples in TRAIN split — cannot train Isolation Forest")

    print(
        f"Training Isolation Forest on {len(train_normal)} healthy TRAIN samples "
        f"(of {len(train)} total TRAIN samples) over {len(numeric_features)} numeric features"
    )
    estimator = fit_isolation_forest(
        train_normal,
        preprocessor,
        n_estimators=config.n_estimators,
        contamination=config.contamination,
        seed=config.seed,
    )

    artifact = AnomalyModelArtifact(
        estimator=estimator,
        preprocessor=preprocessor,
        numeric_features=numeric_features,
        minimum_required_features=config.minimum_required_features,
        threshold=0.0,
    )

    validation_normal = [s for s in validation if s.label == FailureLabel.NORMAL]
    if not validation_normal:
        raise SystemExit(
            "no NORMAL-labeled samples in VALIDATION split — cannot calibrate threshold"
        )
    validation_scores = artifact.anomaly_scores(validation_normal)
    threshold = float(np.quantile(validation_scores, 1.0 - config.target_validation_fpr))
    artifact.threshold = threshold

    evaluation = evaluate_anomaly_model(
        artifact,
        test,
        persistence_n=config.persistence_n,
        persistence_m=config.persistence_m,
        severe_severity_threshold=config.severe_severity_threshold,
    )

    # Documented VALIDATED gate: healthy false-positive rate stays within 2.5x its
    # validation target on unseen TEST data, and at least half of the distinct TEST fault
    # scenarios are detected at all (some detection, not necessarily perfect recall) — a
    # deliberately modest bar appropriate to a bounded synthetic dataset (Phase 11 brief
    # §25: Phase 11 never auto-promotes past VALIDATED; this only decides EXPERIMENT vs.
    # VALIDATED, never STAGING/PRODUCTION).
    scenario_rates = evaluation.detection_rate_by_scenario
    detected_fraction = (
        sum(1 for r in scenario_rates.values() if r > 0) / len(scenario_rates)
        if scenario_rates
        else 0.0
    )
    status = ModelLifecycleState.EXPERIMENT
    if (
        evaluation.healthy_false_positive_rate <= config.target_validation_fpr * 2.5
        and detected_fraction >= 0.5
    ):
        status = ModelLifecycleState.VALIDATED

    metadata = ModelMetadata(
        model_id=config.model_id,
        model_version=config.model_version,
        model_type=ModelType.ANOMALY_ISOLATION_FOREST,
        training_time=datetime.now(UTC),
        dataset_id=manifest.dataset_id,
        dataset_version=manifest.dataset_version,
        feature_set=config.feature_set,
        feature_set_version=config.feature_set_version,
        features=numeric_features,
        hyperparameters={
            "n_estimators": config.n_estimators,
            "contamination": config.contamination,
        },
        metrics=evaluation.to_dict(),
        thresholds={
            "anomaly_score": threshold,
            "target_validation_fpr": config.target_validation_fpr,
        },
        seed=config.seed,
        code_version=__code_version__,
        status=status,
        limitations=(
            "trained on a modest synthetic dataset generated from a bounded number of "
            "simulator scenario runs; not validated for production machinery",
        ),
        minimum_required_features=config.minimum_required_features,
    )

    registry = ModelRegistry(args.artifacts_dir)
    registered = registry.register(artifact, metadata)

    args.evaluation_out.parent.mkdir(parents=True, exist_ok=True)
    args.evaluation_out.write_text(
        json.dumps(
            {"metadata": registered.to_dict(), "evaluation": evaluation.to_dict()},
            indent=2,
            default=str,
        )
    )

    print(f"Registered {config.model_id}@{config.model_version} status={status.value}")
    print(
        f"threshold={threshold:.4f} healthy_fpr={evaluation.healthy_false_positive_rate:.4f} "
        f"pr_auc={evaluation.pr_auc:.4f} binary_recall={evaluation.binary_recall:.4f}"
    )
    print(f"detection_rate_by_scenario={evaluation.detection_rate_by_scenario}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
