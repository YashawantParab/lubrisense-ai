"""Merges the anomaly/classifier evaluation JSONs plus the dataset manifest into one
git-tracked, machine-readable evaluation artifact (Phase 11 brief §71):

    python scripts/build_evaluation_report.py --dataset-dir data/datasets/PHASE11_REFERENCE

All numbers in the resulting file are copied verbatim from real training/evaluation runs —
nothing here is computed or fabricated; this script only merges existing JSON.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument(
        "--out", type=Path, default=REPO_ROOT / "docs" / "results" / "model_evaluation.json"
    )
    args = parser.parse_args()

    manifest = json.loads((args.dataset_dir / "manifest.json").read_text())
    anomaly = json.loads(
        (ROOT / "artifacts" / "evaluation" / "anomaly_evaluation.json").read_text()
    )
    classifier = json.loads(
        (ROOT / "artifacts" / "evaluation" / "classifier_evaluation.json").read_text()
    )

    report = {
        "dataset_manifest": manifest,
        "anomaly_model": anomaly,
        "classifier_models": classifier,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, default=str))
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
