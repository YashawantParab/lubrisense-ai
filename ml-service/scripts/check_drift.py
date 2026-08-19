"""Reference drift/coverage check (Phase 32 brief §32.8) — NOT a production monitoring
system (no scheduler, no alerting, no persisted score history). Compares TRAIN (the
"reference" distribution a model was trained on) against TEST (the most temporally-recent
held-out batch) from an already-built dataset directory, or any two dataset directories
you point it at.

    python scripts/check_drift.py --dataset-dir data/datasets/FAILURE_CLASSIFICATION_V1
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ml_service.datasets.builder import DatasetBuilder
from ml_service.domain.dataset import SplitName
from ml_service.monitoring.drift import compute_drift_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument(
        "--current-dataset-dir",
        type=Path,
        default=None,
        help="if omitted, compares this dataset's own TRAIN (reference) vs TEST (current)",
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    manifest, samples = DatasetBuilder.load(args.dataset_dir)
    feature_names = list(manifest.feature_list)

    if args.current_dataset_dir:
        _, current_samples = DatasetBuilder.load(args.current_dataset_dir)
        reference_samples = samples
        mode = f"{args.dataset_dir} (all) vs {args.current_dataset_dir} (all)"
    else:
        reference_samples = [s for s in samples if s.split == SplitName.TRAIN]
        current_samples = [s for s in samples if s.split == SplitName.TEST]
        mode = f"{args.dataset_dir} TRAIN (reference) vs TEST (current)"

    report = compute_drift_report(reference_samples, current_samples, feature_names)
    print(f"Drift check: {mode}")
    print(f"  reference_sample_count={report.reference_sample_count}  "
          f"current_sample_count={report.current_sample_count}")
    print(f"  reference_coverage={report.reference_coverage:.3f}  "
          f"current_coverage={report.current_coverage:.3f}")
    if report.substantial_shift_features:
        print(f"  SUBSTANTIAL_SHIFT features: {list(report.substantial_shift_features)}")
    else:
        print("  no feature crossed the SUBSTANTIAL_SHIFT (PSI >= 0.25) threshold")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report.to_dict(), indent=2))
        print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
