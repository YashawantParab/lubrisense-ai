"""Builds a leakage-safe dataset from every run manifest in `data/runs/` for one feature
set, using the second (independently equipped) asset's runs as a forced TEST holdout for
the asset-generalization test:

    python scripts/build_dataset.py --feature-set LUBRICATION_ANOMALY_V1 \
        --feature-set-version 1.0.2 --out data/datasets/LUBRICATION_ANOMALY_V1
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ml_service.datasets.builder import BuildConfig, DatasetBuilder

DEFAULT_RUNS_DIR = Path(__file__).resolve().parents[1] / "data" / "runs"

#: Always TEST, regardless of timestamp order or stratified-group placement:
#: - the second, otherwise-independent equipped asset's runs (Phase 11 brief §31 asset
#:   generalization);
#: - the sole multi-fault-composition run (its two constituent single-fault labels are
#:   otherwise covered in TRAIN by restriction-1/2 and bearing-fault-1, so this run is more
#:   valuable as the required multi-fault TEST evaluation case, §55, than as TRAIN data for
#:   a combination a single-label classifier cannot represent correctly anyway);
#: - the sole connectivity-loss run (excluded from supervised training entirely; only used
#:   for anomaly-model / graceful-degradation robustness evaluation, so TEST is strictly
#:   more useful than TRAIN).
FORCED_TEST_RUN_IDS = frozenset(
    {
        "healthy-second-asset-1",
        "restriction-second-asset-1",
        "multi-fault-1",
        "network-failure-1",
    }
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a Phase 11 leakage-safe dataset.")
    parser.add_argument("--feature-set", required=True)
    parser.add_argument("--feature-set-version", required=True)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dataset-id", default="PHASE11_REFERENCE")
    parser.add_argument("--dataset-version", default="1.0.0")
    args = parser.parse_args()

    run_manifests = [
        DatasetBuilder.load_run_manifest(p) for p in sorted(args.runs_dir.glob("*.json"))
    ]
    if not run_manifests:
        raise SystemExit(f"no run manifests found in {args.runs_dir}")
    print(f"Loaded {len(run_manifests)} run manifests from {args.runs_dir}")

    config = BuildConfig(
        feature_set=args.feature_set,
        feature_set_version=args.feature_set_version,
        force_test_run_ids=FORCED_TEST_RUN_IDS,
        dataset_id=args.dataset_id,
        dataset_version=args.dataset_version,
    )
    builder = DatasetBuilder()
    manifest, samples = builder.build(run_manifests, config)
    DatasetBuilder.save(manifest, samples, args.out)

    print(f"Built dataset {manifest.dataset_id}@{manifest.dataset_version}")
    print(f"  sample_count={manifest.sample_count}")
    print(f"  class_distribution_raw={manifest.class_distribution_raw}")
    print(f"  split_counts={manifest.split_counts}")
    audit = manifest.leakage_audit
    print(f"  leakage_audit.passed={audit.passed if audit else None}")
    print(f"  leakage_audit.proxy_suspects={audit.proxy_suspects if audit else None}")
    print(f"Saved to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
