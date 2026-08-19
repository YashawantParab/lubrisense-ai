import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ml_service.domain.model_metadata import ModelLifecycleState, ModelMetadata, ModelType
from ml_service.registry.registry import ModelRegistry

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from promote_model import PromotionRefusedError, promote  # noqa: E402


def _metadata(status: ModelLifecycleState) -> ModelMetadata:
    return ModelMetadata(
        model_id="LUBRICATION_ANOMALY_V1",
        model_version="1.0.0",
        model_type=ModelType.ANOMALY_ISOLATION_FOREST,
        training_time=datetime(2026, 1, 1, tzinfo=UTC),
        dataset_id="PHASE11_REFERENCE",
        dataset_version="1.0.0",
        feature_set="LUBRICATION_ANOMALY_V1",
        feature_set_version="1.0.2",
        features=("pressure.current",),
        hyperparameters={},
        metrics={"pr_auc": 0.84},
        thresholds={},
        seed=42,
        code_version="0.1.0",
        status=status,
        limitations=(),
    )


def test_promote_validated_to_staging_succeeds(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    registry.register({"v": 1}, _metadata(ModelLifecycleState.VALIDATED))

    record = promote(
        registry,
        model_id="LUBRICATION_ANOMALY_V1",
        version="1.0.0",
        to_status=ModelLifecycleState.STAGING,
        actor="demo-admin",
        reason="cleared the validation gate",
    )
    assert record["to_status"] == "STAGING"
    assert registry.get_metadata("LUBRICATION_ANOMALY_V1", "1.0.0").status == (
        ModelLifecycleState.STAGING
    )

    log_lines = (tmp_path / "promotion_log.jsonl").read_text().strip().splitlines()
    assert len(log_lines) == 1
    logged = json.loads(log_lines[0])
    assert logged["actor"] == "demo-admin"
    assert logged["from_status"] == "VALIDATED"


def test_promote_refuses_stage_skip(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    registry.register({"v": 1}, _metadata(ModelLifecycleState.EXPERIMENT))

    with pytest.raises(PromotionRefusedError, match="not an allowed transition"):
        promote(
            registry,
            model_id="LUBRICATION_ANOMALY_V1",
            version="1.0.0",
            to_status=ModelLifecycleState.PRODUCTION,
            actor="demo-admin",
            reason="skip ahead",
        )
    # No log entry written for a refused promotion.
    assert not (tmp_path / "promotion_log.jsonl").exists()


def test_promote_refuses_empty_reason(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    registry.register({"v": 1}, _metadata(ModelLifecycleState.VALIDATED))

    with pytest.raises(PromotionRefusedError, match="reason is required"):
        promote(
            registry,
            model_id="LUBRICATION_ANOMALY_V1",
            version="1.0.0",
            to_status=ModelLifecycleState.STAGING,
            actor="demo-admin",
            reason="   ",
        )


def test_promote_refuses_unregistered_model(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    with pytest.raises(PromotionRefusedError, match="not registered"):
        promote(
            registry,
            model_id="NOPE",
            version="1.0.0",
            to_status=ModelLifecycleState.STAGING,
            actor="demo-admin",
            reason="anything",
        )


def test_retirement_allowed_from_any_non_retired_stage(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    registry.register({"v": 1}, _metadata(ModelLifecycleState.PRODUCTION))
    promote(
        registry,
        model_id="LUBRICATION_ANOMALY_V1",
        version="1.0.0",
        to_status=ModelLifecycleState.RETIRED,
        actor="demo-admin",
        reason="superseded by a newer version",
    )
    assert registry.get_metadata("LUBRICATION_ANOMALY_V1", "1.0.0").status == (
        ModelLifecycleState.RETIRED
    )
