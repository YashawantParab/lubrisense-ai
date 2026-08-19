# ML Service

Owns model training, evaluation, explainability, and inference for Machine & Sensor
Intelligence evidence: unsupervised anomaly detection (`LUBRICATION_ANOMALY_V1`, Isolation
Forest) and supervised failure-mode classification (`FAILURE_CLASSIFICATION_V1`, baseline
logistic regression + primary `HistGradientBoostingClassifier`). Kept as a separate service
from `backend/` so model logic never lives inside API route handlers
(`TECHNICAL_DECISIONS.md` ADR-011, ADR-090).

**Phase 11 status: implemented.** See `docs/ML_ARCHITECTURE.md` for the full design and
`docs/MODEL_CARD.md` for what the trained models are (and are not) validated for. ML output
here is evidence for a future Condition Intelligence layer — never a diagnosis or
maintenance decision.

## Layout

```
ml_service/
  domain/            label schema, dataset/model-metadata/inference contracts
  datasets/           feature-vector reader, ground-truth reader, leakage-safe builder/splitter/audit
  training/            model-specific feature selection, preprocessing, training CLIs
  models/              AnomalyModelArtifact, ClassifierModelArtifact wrappers
  evaluation/           metrics, anomaly/classifier evaluation
  explainability/       feature-ablation and z-score attribution
  registry/             filesystem model registry
  inference/            InferenceService — the only place a model is scored
  config/               versioned YAML config loader
config/                anomaly_v1.yaml, classifier_v1.yaml
artifacts/              model.joblib + metadata.json per model/version (gitignored)
data/                   generated run manifests + ground truth JSONL + built datasets (gitignored)
```

## Generating the reference dataset

Requires the full Docker Compose stack running (`docker compose up`) with demo data seeded
(`make seed`):

```bash
cd edge && uv run python scripts/generate_ml_training_data.py --output-dir ../ml-service/data
```

Drives real simulator scenario runs through the real edge/MQTT/Kafka/TimescaleDB pipeline
and captures ground truth locally. Then materialize Phase 10 feature vectors for each run
(see each `data/runs/*.json` manifest for its machine/time range):

```bash
cd backend && uv run python -m app.features.materialize \
  --machine-id <machine_id> --tenant-id <tenant_id> \
  --feature-set LUBRICATION_ANOMALY_V1 --start <start> --end <end> --interval-seconds 300
```

## Building a dataset and training

```python
from pathlib import Path
from ml_service.datasets.builder import BuildConfig, DatasetBuilder

builder = DatasetBuilder()
run_manifests = [
    DatasetBuilder.load_run_manifest(p) for p in Path("data/runs").glob("*.json")
]
config = BuildConfig(
    feature_set="LUBRICATION_ANOMALY_V1",
    feature_set_version="1.0.2",
    force_test_run_ids=frozenset({"healthy-second-asset-1", "restriction-second-asset-1"}),
)
manifest, samples = builder.build(run_manifests, config)
DatasetBuilder.save(manifest, samples, Path("data/datasets/LUBRICATION_ANOMALY_V1"))
```

```bash
python -m ml_service.training.train_anomaly --dataset-dir data/datasets/LUBRICATION_ANOMALY_V1
python -m ml_service.training.train_classifier --dataset-dir data/datasets/FAILURE_CLASSIFICATION_V1
python scripts/build_evaluation_report.py --dataset-dir data/datasets/FAILURE_CLASSIFICATION_V1
```

## Tests

```bash
uv run pytest
```

All tests are pure-Python (no live Docker/Postgres dependency) — they use synthetic
`DatasetSample`/`FeatureSnapshot` fixtures, not the live pipeline. The live pipeline is
exercised by `edge/scripts/generate_ml_training_data.py` and
`scripts/verify_ml_pipeline.py` (run against the live stack).
