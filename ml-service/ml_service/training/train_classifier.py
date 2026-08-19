"""Reproducible training command (Phase 11 brief §21):

    python -m ml_service.training.train_classifier --dataset-dir data/datasets/PHASE11_REFERENCE

Trains both a baseline (multinomial logistic regression) and the primary
(HistGradientBoostingClassifier) supervised classifier on the same TRAIN/VALIDATION/TEST
split and preprocessing, so the primary model's benefit over the baseline is a real,
measured comparison (Phase 11 brief §16, §50), not an assumption.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.utils.class_weight import compute_sample_weight

from ml_service import __code_version__
from ml_service.config.loader import ClassifierConfig, load_classifier_config
from ml_service.datasets.builder import DatasetBuilder
from ml_service.domain.dataset import DatasetManifest, DatasetSample, SplitName
from ml_service.domain.model_metadata import ModelLifecycleState, ModelMetadata, ModelType
from ml_service.evaluation.evaluate_classifier import (
    ClassifierEvaluationResult,
    evaluate_classifier,
)
from ml_service.models.classifier import ClassifierModelArtifact
from ml_service.registry.registry import ModelRegistry
from ml_service.training.feature_sets import (
    CLASSIFIER_CATEGORICAL_FEATURES,
    CLASSIFIER_EXCLUDED_FEATURES,
    select_feature_names,
)
from ml_service.training.preprocessing import Preprocessor

_DEFAULT_EVAL_PATH = (
    Path(__file__).resolve().parents[2] / "artifacts" / "evaluation" / "classifier_evaluation.json"
)


def _build_preprocessor(
    manifest: DatasetManifest, train: list[DatasetSample]
) -> tuple[Preprocessor, tuple[str, ...]]:
    selected = select_feature_names(manifest.feature_list, CLASSIFIER_EXCLUDED_FEATURES)
    categorical = tuple(f for f in selected if f in CLASSIFIER_CATEGORICAL_FEATURES)
    numeric = tuple(f for f in selected if f not in CLASSIFIER_CATEGORICAL_FEATURES)
    preprocessor = Preprocessor(numeric_features=numeric, categorical_features=categorical)
    preprocessor.fit(train)
    return preprocessor, selected


def _train_one(
    estimator: object,
    preprocessor: Preprocessor,
    train: list[DatasetSample],
    *,
    use_sample_weight: bool,
) -> object:
    x = preprocessor.transform(train)
    y = [s.label.value for s in train]
    if use_sample_weight:
        weights = compute_sample_weight("balanced", y)
        estimator.fit(x, y, sample_weight=weights)  # type: ignore[attr-defined]
    else:
        estimator.fit(x, y)  # type: ignore[attr-defined]
    return estimator


def _artifact(
    estimator: object,
    preprocessor: Preprocessor,
    numeric: tuple[str, ...],
    categorical: tuple[str, ...],
    config: ClassifierConfig,
) -> ClassifierModelArtifact:
    return ClassifierModelArtifact(
        estimator=estimator,  # type: ignore[arg-type]
        preprocessor=preprocessor,
        feature_names=numeric + categorical,
        categorical_features=categorical,
        minimum_required_features=config.minimum_required_features,
        class_order=tuple(estimator.classes_),  # type: ignore[attr-defined]
        unknown_confidence_threshold=config.unknown_confidence_threshold,
    )


def _register(
    registry: ModelRegistry,
    model_id: str,
    model_type: ModelType,
    artifact: ClassifierModelArtifact,
    evaluation: ClassifierEvaluationResult,
    manifest: DatasetManifest,
    config: ClassifierConfig,
    status: ModelLifecycleState,
) -> ModelMetadata:
    metadata = ModelMetadata(
        model_id=model_id,
        model_version=config.model_version,
        model_type=model_type,
        training_time=datetime.now(UTC),
        dataset_id=manifest.dataset_id,
        dataset_version=manifest.dataset_version,
        feature_set=config.feature_set,
        feature_set_version=config.feature_set_version,
        features=artifact.feature_names,
        hyperparameters={},
        metrics=evaluation.to_dict(),
        thresholds={
            "unknown_confidence_threshold": config.unknown_confidence_threshold,
            "moderate": config.confidence_moderate_threshold,
            "high": config.confidence_high_threshold,
        },
        seed=config.seed,
        code_version=__code_version__,
        status=status,
        limitations=(
            "trained on a modest synthetic dataset generated from a bounded number of "
            "simulator scenario runs; single-label classifier cannot represent true "
            "multi-fault ground truth; not validated for production machinery",
        ),
        minimum_required_features=config.minimum_required_features,
    )
    return registry.register(artifact, metadata)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Train baseline + primary FAILURE_CLASSIFICATION_V1."
    )
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--artifacts-dir", type=Path, default=None)
    parser.add_argument("--evaluation-out", type=Path, default=_DEFAULT_EVAL_PATH)
    args = parser.parse_args()

    config = load_classifier_config(args.config)
    manifest, samples = DatasetBuilder.load(args.dataset_dir)

    train = [s for s in samples if s.split == SplitName.TRAIN]
    validation = [s for s in samples if s.split == SplitName.VALIDATION]
    test = [s for s in samples if s.split == SplitName.TEST]
    if not train or not validation or not test:
        raise SystemExit(
            f"dataset must have non-empty TRAIN/VALIDATION/TEST splits, got "
            f"{len(train)}/{len(validation)}/{len(test)}"
        )

    preprocessor, selected = _build_preprocessor(manifest, train)
    numeric = tuple(f for f in selected if f not in CLASSIFIER_CATEGORICAL_FEATURES)
    categorical = tuple(f for f in selected if f in CLASSIFIER_CATEGORICAL_FEATURES)
    print(
        f"Training classifiers on {len(train)} TRAIN samples "
        f"({len(numeric)} numeric + {len(categorical)} categorical features)"
    )

    label_counts = {
        label: sum(1 for s in train if s.label.value == label)
        for label in {s.label.value for s in train}
    }
    print(f"TRAIN raw class distribution: {label_counts}")

    baseline_estimator = LogisticRegression(
        max_iter=config.baseline.max_iter,
        class_weight=config.baseline.class_weight,
        random_state=config.baseline.seed,
    )
    _train_one(baseline_estimator, preprocessor, train, use_sample_weight=False)
    baseline_artifact = _artifact(baseline_estimator, preprocessor, numeric, categorical, config)

    primary_estimator = HistGradientBoostingClassifier(
        max_iter=config.primary.max_iter,
        max_depth=config.primary.max_depth,
        learning_rate=config.primary.learning_rate,
        l2_regularization=config.primary.l2_regularization,
        random_state=config.primary.seed,
    )
    _train_one(primary_estimator, preprocessor, train, use_sample_weight=True)
    primary_artifact = _artifact(primary_estimator, preprocessor, numeric, categorical, config)

    baseline_eval = evaluate_classifier(
        baseline_artifact, test, train_samples=train, validation_samples=validation
    )
    primary_eval = evaluate_classifier(
        primary_artifact, test, train_samples=train, validation_samples=validation
    )

    print(
        f"BASELINE  test macro_f1={baseline_eval.report.macro_f1:.4f} "
        f"weighted_f1={baseline_eval.report.weighted_f1:.4f}"
    )
    print(
        f"PRIMARY   test macro_f1={primary_eval.report.macro_f1:.4f} "
        f"weighted_f1={primary_eval.report.weighted_f1:.4f}"
    )

    n_classes = len({s.label.value for s in train} | {s.label.value for s in test})
    random_floor = 1.0 / max(n_classes, 1)

    # Overfitting check (Phase 11 brief §51): a VALIDATED classifier's TRAIN macro F1 must
    # not wildly exceed its TEST macro F1.
    primary_gap = (
        primary_eval.train_report.macro_f1 - primary_eval.report.macro_f1
        if primary_eval.train_report
        else 0.0
    )
    primary_status = ModelLifecycleState.EXPERIMENT
    if (
        primary_eval.report.macro_f1 >= max(baseline_eval.report.macro_f1, random_floor * 1.5)
        and primary_gap <= 0.35
    ):
        primary_status = ModelLifecycleState.VALIDATED

    baseline_status = (
        ModelLifecycleState.VALIDATED
        if baseline_eval.report.macro_f1 >= random_floor * 1.2
        else ModelLifecycleState.EXPERIMENT
    )

    registry = ModelRegistry(args.artifacts_dir)
    registered_baseline = _register(
        registry,
        "FAILURE_CLASSIFICATION_BASELINE_V1",
        ModelType.CLASSIFIER_BASELINE_LOGISTIC_REGRESSION,
        baseline_artifact,
        baseline_eval,
        manifest,
        config,
        baseline_status,
    )
    registered_primary = _register(
        registry,
        config.model_id,
        ModelType.CLASSIFIER_PRIMARY_HIST_GRADIENT_BOOSTING,
        primary_artifact,
        primary_eval,
        manifest,
        config,
        primary_status,
    )

    args.evaluation_out.parent.mkdir(parents=True, exist_ok=True)
    args.evaluation_out.write_text(
        json.dumps(
            {
                "baseline": {
                    "metadata": registered_baseline.to_dict(),
                    "evaluation": baseline_eval.to_dict(),
                },
                "primary": {
                    "metadata": registered_primary.to_dict(),
                    "evaluation": primary_eval.to_dict(),
                },
                "comparison": {
                    "baseline_test_macro_f1": baseline_eval.report.macro_f1,
                    "primary_test_macro_f1": primary_eval.report.macro_f1,
                    "primary_beats_baseline": primary_eval.report.macro_f1
                    >= baseline_eval.report.macro_f1,
                    "primary_train_test_macro_f1_gap": primary_gap,
                    "random_floor_macro_f1": random_floor,
                },
            },
            indent=2,
            default=str,
        )
    )

    print(
        f"Registered baseline status={baseline_status.value}, primary status={primary_status.value}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
