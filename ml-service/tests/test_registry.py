from datetime import UTC, datetime
from pathlib import Path

import pytest

from ml_service.domain.model_metadata import ModelLifecycleState, ModelMetadata, ModelType
from ml_service.registry.registry import (
    ArtifactIntegrityError,
    ModelNotFoundError,
    ModelRegistry,
)


def _metadata(version: str, status: ModelLifecycleState, training_time: datetime) -> ModelMetadata:
    return ModelMetadata(
        model_id="LUBRICATION_ANOMALY_V1",
        model_version=version,
        model_type=ModelType.ANOMALY_ISOLATION_FOREST,
        training_time=training_time,
        dataset_id="PHASE11_REFERENCE",
        dataset_version="1.0.0",
        feature_set="LUBRICATION_ANOMALY_V1",
        feature_set_version="1.0.2",
        features=("pressure.current",),
        hyperparameters={"n_estimators": 200},
        metrics={"validation_fpr": 0.05},
        thresholds={"anomaly_score": 0.6},
        seed=42,
        code_version="0.1.0",
        status=status,
        limitations=("synthetic data only",),
    )


def test_register_then_load_round_trip(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    metadata = _metadata("1.0.0", ModelLifecycleState.VALIDATED, datetime(2026, 1, 1, tzinfo=UTC))
    artifact = {"fake": "estimator"}
    registry.register(artifact, metadata)

    loaded_artifact, loaded_metadata = registry.load("LUBRICATION_ANOMALY_V1", "1.0.0")
    assert loaded_artifact == artifact
    assert loaded_metadata.model_version == "1.0.0"
    assert loaded_metadata.status == ModelLifecycleState.VALIDATED
    assert loaded_metadata.artifact_path.endswith("model.joblib")


def test_load_unknown_version_raises() -> None:
    registry = ModelRegistry(Path("/tmp/does-not-matter"))
    import pytest

    with pytest.raises(ModelNotFoundError):
        registry.get_metadata("NOPE", "1.0.0")


def test_latest_by_status_uses_index_training_time_not_filesystem(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    registry.register(
        {"v": 1},
        _metadata("1.0.0", ModelLifecycleState.VALIDATED, datetime(2026, 1, 1, tzinfo=UTC)),
    )
    registry.register(
        {"v": 2},
        _metadata("2.0.0", ModelLifecycleState.EXPERIMENT, datetime(2026, 2, 1, tzinfo=UTC)),
    )
    registry.register(
        {"v": 3},
        _metadata("1.5.0", ModelLifecycleState.VALIDATED, datetime(2026, 1, 15, tzinfo=UTC)),
    )

    latest_validated = registry.latest_by_status(
        "LUBRICATION_ANOMALY_V1", (ModelLifecycleState.VALIDATED,)
    )
    assert latest_validated is not None
    # 2.0.0 is newest overall but EXPERIMENT — must not be returned when filtering to VALIDATED
    assert latest_validated.model_version == "1.5.0"


def test_never_auto_promotes_to_production(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    metadata = _metadata("1.0.0", ModelLifecycleState.VALIDATED, datetime(2026, 1, 1, tzinfo=UTC))
    registry.register({"v": 1}, metadata)
    reloaded = registry.get_metadata("LUBRICATION_ANOMALY_V1", "1.0.0")
    assert reloaded.status != ModelLifecycleState.PRODUCTION


def test_register_computes_artifact_checksum(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    metadata = _metadata("1.0.0", ModelLifecycleState.VALIDATED, datetime(2026, 1, 1, tzinfo=UTC))
    registered = registry.register({"v": 1}, metadata)
    assert len(registered.artifact_checksum) == 64  # sha256 hex digest

    _, loaded_metadata = registry.load("LUBRICATION_ANOMALY_V1", "1.0.0")
    assert loaded_metadata.artifact_checksum == registered.artifact_checksum


def test_load_detects_corrupted_artifact(tmp_path: Path) -> None:
    import joblib

    registry = ModelRegistry(tmp_path)
    metadata = _metadata("1.0.0", ModelLifecycleState.VALIDATED, datetime(2026, 1, 1, tzinfo=UTC))
    registry.register({"v": 1}, metadata)

    # Swap in a different, still-valid artifact file — simulates an out-of-band file
    # replacement, which is exactly what the checksum check exists to catch (a scrambled
    # byte stream would fail at `joblib.load` regardless of the checksum check).
    artifact_path = tmp_path / "LUBRICATION_ANOMALY_V1" / "1.0.0" / "model.joblib"
    joblib.dump({"swapped": "artifact"}, artifact_path)

    with pytest.raises(ArtifactIntegrityError):
        registry.load("LUBRICATION_ANOMALY_V1", "1.0.0")

    # Explicitly opting out of verification still loads (e.g. for forensic inspection).
    artifact, _ = registry.load("LUBRICATION_ANOMALY_V1", "1.0.0", verify_checksum=False)
    assert artifact == {"swapped": "artifact"}


def test_set_status_updates_metadata_and_index(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    metadata = _metadata("1.0.0", ModelLifecycleState.EXPERIMENT, datetime(2026, 1, 1, tzinfo=UTC))
    registry.register({"v": 1}, metadata)
    registry.set_status("LUBRICATION_ANOMALY_V1", "1.0.0", ModelLifecycleState.VALIDATED)
    reloaded = registry.get_metadata("LUBRICATION_ANOMALY_V1", "1.0.0")
    assert reloaded.status == ModelLifecycleState.VALIDATED
    entries = registry.list_versions("LUBRICATION_ANOMALY_V1")
    assert entries[0].status == ModelLifecycleState.VALIDATED
