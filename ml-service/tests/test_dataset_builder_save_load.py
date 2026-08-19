import uuid
from datetime import UTC, datetime
from pathlib import Path

from ml_service.datasets.builder import DatasetBuilder
from ml_service.datasets.leakage_audit import run_leakage_audit
from ml_service.domain.dataset import DatasetManifest, DatasetSample, SplitName
from ml_service.domain.labels import FailureLabel

TENANT = uuid.uuid4()
MACHINE = uuid.uuid4()


def _sample() -> DatasetSample:
    return DatasetSample(
        feature_vector_id=uuid.uuid4(),
        run_id="run-1",
        tenant_id=TENANT,
        machine_id=MACHINE,
        asset_code="L1-7B43-M000",
        as_of_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        feature_set="LUBRICATION_ANOMALY_V1",
        feature_set_version="1.0.2",
        feature_values={"pressure.current": 5.0, "context.load_bucket": "NORMAL"},
        missing_features=("flow.current",),
        quality_summary={"trusted_fraction.15m": 1.0},
        label=FailureLabel.NORMAL,
        source_scenario_type=None,
        ground_truth_severity=0.0,
        split=SplitName.TRAIN,
    )


def test_save_then_load_round_trips_samples_and_manifest(tmp_path: Path) -> None:
    samples = [_sample()]
    audit = run_leakage_audit(samples, ("pressure.current", "context.load_bucket"))
    manifest = DatasetManifest(
        dataset_id="TEST_DS",
        dataset_version="1.0.0",
        feature_set="LUBRICATION_ANOMALY_V1",
        feature_set_version="1.0.2",
        label_schema_version="1.0.0",
        source_assets=("L1-7B43-M000",),
        source_scenarios=("HEALTHY",),
        time_range_start=datetime(2026, 1, 1, tzinfo=UTC),
        time_range_end=datetime(2026, 1, 2, tzinfo=UTC),
        seeds=(1,),
        sample_count=1,
        class_distribution_raw={"NORMAL": 1},
        split_strategy="grouped_by_run_id_time_ordered",
        split_counts={"TRAIN": 1},
        feature_list=("pressure.current", "context.load_bucket"),
        excluded_features=(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        code_version="0.1.0",
        config_version="1.0.0",
        run_manifests=("run-1",),
        leakage_audit=audit,
    )

    out_dir = tmp_path / "ds"
    DatasetBuilder.save(manifest, samples, out_dir)
    loaded_manifest, loaded_samples = DatasetBuilder.load(out_dir)

    assert loaded_manifest.dataset_id == "TEST_DS"
    assert loaded_manifest.leakage_audit is not None
    assert loaded_manifest.leakage_audit.passed is True
    assert len(loaded_samples) == 1
    assert loaded_samples[0].feature_values["pressure.current"] == 5.0
    assert loaded_samples[0].missing_features == ("flow.current",)
    assert loaded_samples[0].label == FailureLabel.NORMAL
