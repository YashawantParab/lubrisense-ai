"""Full-pipeline ML integration check (Phase 11 brief §64):

    Simulator -> Edge -> MQTT -> Kafka -> TimescaleDB -> Data Quality -> Baseline -> Rules
    -> Feature Engineering -> ML inference

Everything up through "Feature Engineering" was already exercised for real by
`edge/scripts/generate_ml_training_data.py` (real simulator scenario runs through the real
edge/MQTT/Kafka/pipeline) and `python -m app.features.materialize` (real Phase 10
`FeatureEngine`, unchanged). This script proves the final hop: a real, currently-VALIDATED
registered model scores a REAL persisted feature vector — not a hand-constructed one — via
the exact `InferenceService` the backend API uses.

Requires: the live Docker Compose stack running, the reference dataset already generated
and materialized, and at least one VALIDATED model registered (`train_anomaly.py`/
`train_classifier.py` already run).

    uv run python scripts/verify_ml_pipeline.py
"""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime

from ml_service.datasets.feature_source import FeatureVectorSource
from ml_service.domain.feature_snapshot import FeatureSnapshot
from ml_service.domain.inference import InferenceStatus
from ml_service.domain.model_metadata import ModelLifecycleState
from ml_service.inference.service import InferenceService
from ml_service.registry.registry import ModelRegistry

FLAGSHIP_TENANT = uuid.UUID("bbdd114e-b5a7-5890-a5bd-9e8c787a5fe0")
FLAGSHIP_MACHINE = uuid.UUID("88551bef-3149-5a8d-9645-bcd9502f4795")

FAILURES = 0


def _pass(msg: str) -> None:
    print(f"  PASS: {msg}")


def _fail(msg: str) -> None:
    global FAILURES  # noqa: PLW0603
    print(f"  FAIL: {msg}", file=sys.stderr)
    FAILURES += 1


def _check_model(model_id: str, feature_set: str) -> None:
    registry = ModelRegistry()
    entry = registry.latest_by_status(
        model_id,
        (
            ModelLifecycleState.VALIDATED,
            ModelLifecycleState.STAGING,
            ModelLifecycleState.PRODUCTION,
        ),
    )
    if entry is None:
        _fail(f"no VALIDATED (or later) version registered for {model_id}")
        return
    print(f"  {model_id}@{entry.model_version} status={entry.status.value}")

    source = FeatureVectorSource()
    metadata = registry.get_metadata(model_id, entry.model_version)
    vectors = source.fetch(
        tenant_id=FLAGSHIP_TENANT,
        machine_id=FLAGSHIP_MACHINE,
        feature_set=feature_set,
        start=datetime(2000, 1, 1, tzinfo=UTC),
        end=datetime(2100, 1, 1, tzinfo=UTC),
    )
    if not vectors:
        _fail(f"no persisted {feature_set} feature vectors found for the flagship machine")
        return
    vector = vectors[len(vectors) // 2]  # a vector from the middle of the dataset, not an edge
    _pass(f"found {len(vectors)} real persisted feature vectors; using {vector.id}")

    snapshot = FeatureSnapshot(
        feature_vector_id=vector.id,
        as_of_timestamp=vector.as_of_timestamp,
        feature_set=vector.feature_set,
        feature_set_version=vector.feature_set_version,
        feature_values=vector.feature_values,
        missing_features=tuple(vector.missing_features),
        quality_summary=vector.quality_summary,
    )

    service = InferenceService(registry)
    if metadata.model_type.value.startswith("ANOMALY"):
        result = service.infer_anomaly(snapshot, model_id, entry.model_version)
        print(
            f"    status={result.status.value} anomaly_score={result.anomaly_score} "
            f"anomalous={result.anomalous}"
        )
        if result.status not in (InferenceStatus.OK, InferenceStatus.INSUFFICIENT_FEATURES):
            _fail(f"unexpected anomaly inference status {result.status}")
        else:
            _pass(
                "real anomaly inference against a real feature vector returned a structured result"
            )
    else:
        result = service.infer_classification(snapshot, model_id, entry.model_version)
        print(
            f"    status={result.status.value} predicted_class={result.predicted_class} "
            f"confidence={result.confidence_category}"
        )
        if result.status not in (
            InferenceStatus.OK,
            InferenceStatus.INSUFFICIENT_FEATURES,
            InferenceStatus.UNKNOWN,
        ):
            _fail(f"unexpected classification inference status {result.status}")
        else:
            _pass(
                "real classification inference against a real feature vector "
                "returned a structured result"
            )


def main() -> int:
    print("=== ML pipeline integration check ===")
    _check_model("LUBRICATION_ANOMALY_V1", "LUBRICATION_ANOMALY_V1")
    _check_model("FAILURE_CLASSIFICATION_V1", "FAILURE_CLASSIFICATION_V1")

    print("")
    if FAILURES == 0:
        print("verify_ml_pipeline PASSED")
        return 0
    print(f"verify_ml_pipeline FAILED: {FAILURES} check(s) failed", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
