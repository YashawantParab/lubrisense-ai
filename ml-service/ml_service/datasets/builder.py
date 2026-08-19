"""`DatasetBuilder` — assembles a versioned, leakage-safe, labeled dataset from persisted
Phase 10 `FeatureVector` rows (features) and simulator ground-truth JSONL (labels only),
per run manifest (Phase 11 brief §3-§8).
"""

from __future__ import annotations

import json
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ml_service import __code_version__, __dataset_config_version__, __label_schema_version__
from ml_service.datasets.feature_source import FeatureVectorSource
from ml_service.datasets.ground_truth import GroundTruthTimeline
from ml_service.datasets.leakage_audit import run_leakage_audit
from ml_service.datasets.splitting import apply_splits, assign_stratified_run_splits
from ml_service.domain.dataset import DatasetManifest, DatasetSample, RunManifest, SplitName
from ml_service.domain.labels import EXCLUDED_FROM_SUPERVISED, FailureLabel, label_for_scenario_type


@dataclass(frozen=True, slots=True)
class BuildConfig:
    feature_set: str
    feature_set_version: str
    max_staleness_seconds: float = 120.0
    train_ratio: float = 0.6
    validation_ratio: float = 0.2
    force_test_run_ids: frozenset[str] = frozenset()
    force_train_run_ids: frozenset[str] = frozenset()
    dataset_id: str = "PHASE11_REFERENCE"
    dataset_version: str = "1.0.0"


def _run_stratum_key(run: RunManifest) -> str:
    """Groups runs for `assign_stratified_run_splits` (Phase 11 brief §31 asset/label
    generalization) by their eventual label so each label's few runs are split
    TRAIN/VALIDATION/TEST independently of unrelated labels' chronological position — see
    `assign_stratified_run_splits`'s docstring for why a single global time-ordered cut is
    unsafe at this dataset's scale. `MULTI_FAULT` and `EXCLUDED` (network-failure-only runs)
    are kept out of any single-label group so they don't dilute that label's TRAIN/TEST
    balance; callers route them to TEST via `force_test_run_ids` when an evaluation (not
    training) case is needed."""
    if not run.scenario_types:
        return "HEALTHY"
    if len(run.scenario_types) > 1:
        return "MULTI_FAULT"
    scenario_type = run.scenario_types[0]
    if scenario_type in EXCLUDED_FROM_SUPERVISED:
        return "EXCLUDED"
    return label_for_scenario_type(scenario_type).value


class DatasetBuilder:
    def __init__(self, database_url: str | None = None) -> None:
        self._source = FeatureVectorSource(database_url)

    def build(
        self, run_manifests: list[RunManifest], config: BuildConfig
    ) -> tuple[DatasetManifest, list[DatasetSample]]:
        if not run_manifests:
            raise ValueError("at least one run manifest is required")

        samples: list[DatasetSample] = []
        dropped = 0
        for run in run_manifests:
            timeline = GroundTruthTimeline.load(Path(run.ground_truth_path))
            vectors = self._source.fetch(
                tenant_id=run.tenant_id,
                machine_id=run.machine_id,
                feature_set=config.feature_set,
                start=run.start_timestamp,
                end=run.end_timestamp,
            )
            for vector in vectors:
                if vector.feature_set_version != config.feature_set_version:
                    continue
                label, source_scenario, severity = timeline.label_at_or_before(
                    vector.as_of_timestamp, config.max_staleness_seconds
                )
                if label is None:
                    dropped += 1
                    continue
                samples.append(
                    DatasetSample(
                        feature_vector_id=vector.id,
                        run_id=run.run_id,
                        tenant_id=vector.tenant_id,
                        machine_id=vector.machine_id,
                        asset_code=run.asset_code,
                        as_of_timestamp=vector.as_of_timestamp,
                        feature_set=vector.feature_set,
                        feature_set_version=vector.feature_set_version,
                        feature_values=dict(vector.feature_values),
                        missing_features=tuple(vector.missing_features),
                        quality_summary=dict(vector.quality_summary),
                        label=label,
                        source_scenario_type=source_scenario,
                        ground_truth_severity=severity,
                        split=SplitName.TRAIN,  # placeholder, overwritten by apply_splits
                    )
                )

        if not samples:
            raise ValueError(
                "no labeled samples produced — check that feature vectors were materialized "
                "for the given run manifests and feature set/version"
            )

        run_split = assign_stratified_run_splits(
            run_manifests,
            _run_stratum_key,
            train_ratio=config.train_ratio,
            validation_ratio=config.validation_ratio,
            force_test_run_ids=config.force_test_run_ids,
            force_train_run_ids=config.force_train_run_ids,
        )
        samples = apply_splits(samples, run_split)

        feature_names = tuple(sorted({name for s in samples for name in s.feature_values}))
        leakage_result = run_leakage_audit(samples, feature_names)

        class_distribution = dict(Counter(s.label.value for s in samples))
        split_counts = dict(Counter(s.split.value for s in samples))

        manifest = DatasetManifest(
            dataset_id=config.dataset_id,
            dataset_version=config.dataset_version,
            feature_set=config.feature_set,
            feature_set_version=config.feature_set_version,
            label_schema_version=__label_schema_version__,
            source_assets=tuple(sorted({r.asset_code for r in run_manifests})),
            source_scenarios=tuple(
                sorted({st for r in run_manifests for st in r.scenario_types} | {"HEALTHY"})
            ),
            time_range_start=min(r.start_timestamp for r in run_manifests),
            time_range_end=max(r.end_timestamp for r in run_manifests),
            seeds=tuple(sorted({r.seed for r in run_manifests})),
            sample_count=len(samples),
            class_distribution_raw=class_distribution,
            split_strategy="grouped_by_run_id_time_ordered",
            split_counts=split_counts,
            feature_list=feature_names,
            excluded_features=(),
            created_at=datetime.now(UTC),
            code_version=__code_version__,
            config_version=__dataset_config_version__,
            run_manifests=tuple(r.run_id for r in run_manifests),
            leakage_audit=leakage_result,
        )
        return manifest, samples

    @staticmethod
    def save(manifest: DatasetManifest, samples: list[DatasetSample], out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "manifest.json").write_text(
            json.dumps(manifest.to_dict(), indent=2, default=str)
        )
        with (out_dir / "samples.jsonl").open("w", encoding="utf-8") as fh:
            for sample in samples:
                row = {
                    "feature_vector_id": str(sample.feature_vector_id),
                    "run_id": sample.run_id,
                    "tenant_id": str(sample.tenant_id),
                    "machine_id": str(sample.machine_id),
                    "asset_code": sample.asset_code,
                    "as_of_timestamp": sample.as_of_timestamp.isoformat(),
                    "feature_set": sample.feature_set,
                    "feature_set_version": sample.feature_set_version,
                    "feature_values": sample.feature_values,
                    "missing_features": list(sample.missing_features),
                    "quality_summary": sample.quality_summary,
                    "label": sample.label.value,
                    "source_scenario_type": sample.source_scenario_type,
                    "ground_truth_severity": sample.ground_truth_severity,
                    "split": sample.split.value,
                }
                fh.write(json.dumps(row, default=str))
                fh.write("\n")

    @staticmethod
    def load(out_dir: Path) -> tuple[DatasetManifest, list[DatasetSample]]:
        manifest_data = json.loads((out_dir / "manifest.json").read_text())
        from ml_service.domain.dataset import LeakageAuditResult  # local import, small struct

        leakage_data = manifest_data.get("leakage_audit")
        manifest = DatasetManifest(
            dataset_id=manifest_data["dataset_id"],
            dataset_version=manifest_data["dataset_version"],
            feature_set=manifest_data["feature_set"],
            feature_set_version=manifest_data["feature_set_version"],
            label_schema_version=manifest_data["label_schema_version"],
            source_assets=tuple(manifest_data["source_assets"]),
            source_scenarios=tuple(manifest_data["source_scenarios"]),
            time_range_start=datetime.fromisoformat(manifest_data["time_range_start"]),
            time_range_end=datetime.fromisoformat(manifest_data["time_range_end"]),
            seeds=tuple(manifest_data["seeds"]),
            sample_count=manifest_data["sample_count"],
            class_distribution_raw=manifest_data["class_distribution_raw"],
            split_strategy=manifest_data["split_strategy"],
            split_counts=manifest_data["split_counts"],
            feature_list=tuple(manifest_data["feature_list"]),
            excluded_features=tuple(manifest_data["excluded_features"]),
            created_at=datetime.fromisoformat(manifest_data["created_at"]),
            code_version=manifest_data["code_version"],
            config_version=manifest_data["config_version"],
            run_manifests=tuple(manifest_data.get("run_manifests", ())),
            leakage_audit=(
                LeakageAuditResult(
                    forbidden_features_found=tuple(leakage_data["forbidden_features_found"]),
                    proxy_suspects=tuple(leakage_data["proxy_suspects"]),
                    passed=leakage_data["passed"],
                )
                if leakage_data
                else None
            ),
        )

        samples: list[DatasetSample] = []
        with (out_dir / "samples.jsonl").open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                samples.append(
                    DatasetSample(
                        feature_vector_id=uuid.UUID(row["feature_vector_id"]),
                        run_id=row["run_id"],
                        tenant_id=uuid.UUID(row["tenant_id"]),
                        machine_id=uuid.UUID(row["machine_id"]),
                        asset_code=row["asset_code"],
                        as_of_timestamp=datetime.fromisoformat(row["as_of_timestamp"]),
                        feature_set=row["feature_set"],
                        feature_set_version=row["feature_set_version"],
                        feature_values=row["feature_values"],
                        missing_features=tuple(row["missing_features"]),
                        quality_summary=row["quality_summary"],
                        label=FailureLabel(row["label"]),
                        source_scenario_type=row["source_scenario_type"],
                        ground_truth_severity=row["ground_truth_severity"],
                        split=SplitName(row["split"]),
                    )
                )
        return manifest, samples

    @staticmethod
    def load_run_manifest(path: Path) -> RunManifest:
        data = json.loads(path.read_text())
        return RunManifest(
            run_id=data["run_id"],
            tenant_id=uuid.UUID(data["tenant_id"]),
            machine_id=uuid.UUID(data["machine_id"]),
            asset_code=data["asset_code"],
            seed=data["seed"],
            scenario_types=tuple(data["scenario_types"]),
            start_timestamp=datetime.fromisoformat(data["start_timestamp"]),
            end_timestamp=datetime.fromisoformat(data["end_timestamp"]),
            ground_truth_path=data["ground_truth_path"],
            is_healthy=data["is_healthy"],
        )
