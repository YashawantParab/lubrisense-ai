"""Model version comparison (Phase 32 brief §32.6).

Compares two registered model versions on macro/weighted F1, per-class recall, healthy
false-positive rate (anomaly models), artifact size, and measured inference latency —
every number either read verbatim from the registered metadata's `metrics` (already
produced by the real training/evaluation run) or measured live against real, persisted
TEST samples from the model's own dataset directory. Nothing here recomputes or estimates
a metric; a model with weak performance is reported exactly as weak, never hidden.

    python scripts/compare_models.py \
        --model-id FAILURE_CLASSIFICATION_BASELINE_V1 --version-a 1.0.0 \
        --model-id-b FAILURE_CLASSIFICATION_V1 --version-b 1.0.0 \
        --dataset-dir data/datasets/FAILURE_CLASSIFICATION_V1
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from ml_service.datasets.builder import DatasetBuilder
from ml_service.domain.dataset import SplitName
from ml_service.models.classifier import ClassifierModelArtifact
from ml_service.registry.registry import DEFAULT_ARTIFACTS_DIR, ModelRegistry


def _artifact_size_bytes(registry: ModelRegistry, model_id: str, version: str) -> int:
    path = registry.base_dir / model_id / version / "model.joblib"
    return path.stat().st_size if path.exists() else -1


def _measure_latency_ms(
    artifact: object, dataset_dir: Path | None, repeats: int = 20
) -> float | None:
    """Measures wall-clock time for one `predict_proba` call over up to 10 real TEST
    samples from the model's own dataset — a real, if small and single-process,
    latency measurement, not a synthetic benchmark claim."""
    if dataset_dir is None or not isinstance(artifact, ClassifierModelArtifact):
        return None
    _, samples = DatasetBuilder.load(dataset_dir)
    test_samples = [s for s in samples if s.split == SplitName.TEST][:10]
    if not test_samples:
        return None
    # Warm-up call (first call may pay one-time JIT/cache costs).
    artifact.predict_proba(test_samples)
    start = time.perf_counter()
    for _ in range(repeats):
        artifact.predict_proba(test_samples)
    elapsed = time.perf_counter() - start
    return (elapsed / repeats) * 1000.0


def _summarize(metadata_metrics: dict[str, object]) -> dict[str, object]:
    summary: dict[str, object] = {}
    test_report = metadata_metrics.get("test_report")
    if isinstance(test_report, dict):
        summary["test_macro_f1"] = test_report.get("macro_f1")
        summary["test_weighted_f1"] = test_report.get("weighted_f1")
        summary["per_class_recall"] = test_report.get("recall")
    if "healthy_false_positive_rate" in metadata_metrics:
        summary["healthy_false_positive_rate"] = metadata_metrics["healthy_false_positive_rate"]
    if "binary_recall" in metadata_metrics:
        summary["binary_recall"] = metadata_metrics["binary_recall"]
    if "pr_auc" in metadata_metrics:
        summary["pr_auc"] = metadata_metrics["pr_auc"]
    if "warning_lead_time_by_run_seconds" in metadata_metrics:
        summary["warning_lead_time_by_run_seconds"] = metadata_metrics[
            "warning_lead_time_by_run_seconds"
        ]
    return summary


def compare(
    registry: ModelRegistry,
    *,
    model_id_a: str,
    version_a: str,
    model_id_b: str,
    version_b: str,
    dataset_dir: Path | None,
) -> dict[str, object]:
    artifact_a, meta_a = registry.load(model_id_a, version_a)
    artifact_b, meta_b = registry.load(model_id_b, version_b)

    return {
        "a": {
            "model_id": model_id_a,
            "version": version_a,
            "status": meta_a.status.value,
            "model_type": meta_a.model_type.value,
            "artifact_size_bytes": _artifact_size_bytes(registry, model_id_a, version_a),
            "artifact_checksum": meta_a.artifact_checksum,
            "measured_inference_latency_ms": _measure_latency_ms(artifact_a, dataset_dir),
            "metrics": _summarize(meta_a.metrics),
        },
        "b": {
            "model_id": model_id_b,
            "version": version_b,
            "status": meta_b.status.value,
            "model_type": meta_b.model_type.value,
            "artifact_size_bytes": _artifact_size_bytes(registry, model_id_b, version_b),
            "artifact_checksum": meta_b.artifact_checksum,
            "measured_inference_latency_ms": _measure_latency_ms(artifact_b, dataset_dir),
            "metrics": _summarize(meta_b.metrics),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", required=True, help="model id for A")
    parser.add_argument("--version-a", required=True)
    parser.add_argument("--model-id-b", required=True)
    parser.add_argument("--version-b", required=True)
    parser.add_argument("--dataset-dir", type=Path, default=None)
    parser.add_argument("--artifacts-dir", type=Path, default=DEFAULT_ARTIFACTS_DIR)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    registry = ModelRegistry(base_dir=args.artifacts_dir)
    result = compare(
        registry,
        model_id_a=args.model_id,
        version_a=args.version_a,
        model_id_b=args.model_id_b,
        version_b=args.version_b,
        dataset_dir=args.dataset_dir,
    )
    text = json.dumps(result, indent=2, default=str)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
        print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
