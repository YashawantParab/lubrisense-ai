"""Dataset contracts (Phase 11 brief §5, §24). Kept free of any simulator/ORM import so the
dataset layer has one clean boundary: `datasets.feature_source` reads persisted Phase 10
`feature_vector` rows over plain SQL (mirrors `simulator.engine.repository.TopologyRepository`'s
own plain-SQL pattern), and `datasets.ground_truth` reads plain JSON ground-truth files.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from ml_service.domain.labels import FailureLabel

type FeatureValue = float | int | bool | str | None


class SplitName(StrEnum):
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    TEST = "TEST"


@dataclass(frozen=True, slots=True)
class RunManifest:
    """One simulator run's provenance — used only for dataset assembly/splitting. `run_id`
    is a grouping key, NEVER a model feature (Phase 11 brief §7)."""

    run_id: str
    tenant_id: uuid.UUID
    machine_id: uuid.UUID
    asset_code: str
    seed: int
    scenario_types: tuple[str, ...]
    start_timestamp: datetime
    end_timestamp: datetime
    ground_truth_path: str
    is_healthy: bool


@dataclass(frozen=True, slots=True)
class DatasetSample:
    """One labeled training/evaluation row. `feature_values`/`missing_features` come
    unmodified from a persisted Phase 10 `FeatureVector` — no simulator field is ever
    merged into `feature_values`. `run_id`/`label`/`source_scenario_type` are label/grouping
    metadata, kept in a separate struct field from `feature_values` so a caller cannot
    accidentally flatten them into the feature matrix."""

    feature_vector_id: uuid.UUID
    run_id: str
    tenant_id: uuid.UUID
    machine_id: uuid.UUID
    asset_code: str
    as_of_timestamp: datetime
    feature_set: str
    feature_set_version: str
    feature_values: dict[str, FeatureValue]
    missing_features: tuple[str, ...]
    quality_summary: dict[str, object]
    label: FailureLabel
    source_scenario_type: str | None
    ground_truth_severity: float
    split: SplitName


@dataclass(frozen=True, slots=True)
class LeakageAuditResult:
    forbidden_features_found: tuple[str, ...]
    proxy_suspects: tuple[str, ...]
    passed: bool


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    dataset_id: str
    dataset_version: str
    feature_set: str
    feature_set_version: str
    label_schema_version: str
    source_assets: tuple[str, ...]
    source_scenarios: tuple[str, ...]
    time_range_start: datetime
    time_range_end: datetime
    seeds: tuple[int, ...]
    sample_count: int
    class_distribution_raw: dict[str, int]
    split_strategy: str
    split_counts: dict[str, int]
    feature_list: tuple[str, ...]
    excluded_features: tuple[str, ...]
    created_at: datetime
    code_version: str
    config_version: str
    run_manifests: tuple[str, ...] = field(default_factory=tuple)
    leakage_audit: LeakageAuditResult | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "feature_set": self.feature_set,
            "feature_set_version": self.feature_set_version,
            "label_schema_version": self.label_schema_version,
            "source_assets": list(self.source_assets),
            "source_scenarios": list(self.source_scenarios),
            "time_range_start": self.time_range_start.isoformat(),
            "time_range_end": self.time_range_end.isoformat(),
            "seeds": list(self.seeds),
            "sample_count": self.sample_count,
            "class_distribution_raw": self.class_distribution_raw,
            "split_strategy": self.split_strategy,
            "split_counts": self.split_counts,
            "feature_list": list(self.feature_list),
            "excluded_features": list(self.excluded_features),
            "created_at": self.created_at.isoformat(),
            "code_version": self.code_version,
            "config_version": self.config_version,
            "run_manifests": list(self.run_manifests),
            "leakage_audit": (
                {
                    "forbidden_features_found": list(self.leakage_audit.forbidden_features_found),
                    "proxy_suspects": list(self.leakage_audit.proxy_suspects),
                    "passed": self.leakage_audit.passed,
                }
                if self.leakage_audit is not None
                else None
            ),
        }
