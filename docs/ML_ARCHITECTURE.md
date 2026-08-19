# ML Architecture — Phase 11

Status: COMPLETE (Phase 11 implementation; verification record in `IMPLEMENTATION_STATUS.md`)

## Purpose

`ml-service` turns versioned Phase 10 feature vectors into ML **evidence**: an anomaly
score and a failure-mode classification, each with an explicit confidence/status and a
structured explanation. It does not diagnose a condition, estimate hidden state, or
recommend maintenance action — those are later phases (Condition Intelligence, Decision
Intelligence). See CLAUDE.md "AI / ML Boundaries" and "Core Product Principle."

**ML output is not a diagnosis.** Anomaly output is never called "failure." Classifier
probabilities are model probabilities, never "truth." Both facts are enforced structurally
in `ml_service.domain.inference` (`InferenceStatus`, `ConfidenceCategory`) and in every
docstring/API field name that touches this output.

## Architecture

```
ml-service/
  ml_service/
    domain/            label schema, dataset/model-metadata/inference contracts
    datasets/           feature-vector reader, ground-truth reader, leakage-safe builder/splitter/audit
    training/            model-specific feature selection, preprocessing, training CLIs
    models/              AnomalyModelArtifact, ClassifierModelArtifact wrappers
    evaluation/           metrics, anomaly/classifier evaluation
    explainability/       feature-ablation and z-score attribution
    registry/             filesystem model registry (explicit version lookup, lifecycle states)
    inference/            InferenceService — the only place a model is scored
    config/               versioned YAML config loader
  config/                anomaly_v1.yaml, classifier_v1.yaml
  artifacts/              model.joblib + metadata.json per model/version (gitignored)
  data/                   generated run manifests + ground truth JSONL (gitignored)
```

`backend/app/ml/` is a thin consumer: it computes the current Phase 10 feature vector
(`FeatureEngine.compute_latest`, unchanged from Phase 10), converts it to a
`ml_service.domain.feature_snapshot.FeatureSnapshot`, calls `ml_service.inference.service.
InferenceService`, and persists the result. No model logic lives in `backend/` — the
service boundary in `TECHNICAL_DECISIONS.md` ADR-011 is unchanged; `backend` now also
depends on `ml-service` as a local editable path dependency, mirroring how `edge` already
depends on `simulator` (ADR: ML service boundary).

## Feature source (train/serve parity)

`ml-service` never recomputes raw telemetry features. Every dataset sample and every
inference input is a persisted Phase 10 `FeatureVector` row (or, at inference time, the
same `FeatureComputationResult` shape Phase 10's `/features/.../latest` endpoint already
returns), read via `ml_service.datasets.feature_source.FeatureVectorSource` (plain
`psycopg`, mirroring `simulator.engine.repository.TopologyRepository`'s own boundary
pattern — `ml-service` does not import the backend's SQLAlchemy ORM).

## Ground truth: labels only, never a feature

Simulator ground truth is read exactly once, in `ml_service.datasets.ground_truth`, from
plain JSONL (the `GroundTruthRecord` shape, read as JSON — `ml_service` does not import the
`simulator` package). It is used exclusively to resolve `ml_service.domain.labels.
FailureLabel` for a sample's `as_of_timestamp`; the resolved label lives in
`DatasetSample.label`, a field structurally separate from `DatasetSample.feature_values`
(see "Leakage audit" below for the proof this separation holds).

### Label schema

```
NORMAL, RESTRICTION, BLOCKAGE, LEAKAGE, PUMP_DEGRADATION, SENSOR_FAULT,
INDEPENDENT_BEARING_ISSUE, UNKNOWN
```

Mapping from simulator `ScenarioType` (`ml_service.domain.labels`):

| Scenario type | Label |
|---|---|
| GRADUAL_RESTRICTION | RESTRICTION |
| SUDDEN_BLOCKAGE | BLOCKAGE |
| LEAKAGE | LEAKAGE |
| PUMP_DEGRADATION | PUMP_DEGRADATION |
| SENSOR_DRIFT, SENSOR_DROPOUT | SENSOR_FAULT |
| INDEPENDENT_BEARING_FAULT | INDEPENDENT_BEARING_ISSUE |
| OVER_LUBRICATION, LOW_RESERVOIR | UNKNOWN (out of the fixed 8-class schema) |
| NETWORK_FAILURE | excluded from supervised labels entirely (data-quality state, not an equipment label) |
| no active scenario | NORMAL |

Multi-fault ticks (more than one scenario simultaneously `DEVELOPING`/`SEVERE`/
`RECOVERING`) resolve to the single highest-severity scenario's label — a documented
limitation (see `docs/MODEL_CARD.md`), not a claim that multi-fault is solved by a
single-label classifier.

## Dataset builder

`ml_service.datasets.builder.DatasetBuilder` takes an explicit list of `RunManifest`
(machine/tenant/asset/seed/scenario types/time range/ground-truth path — produced by
`edge/scripts/generate_ml_training_data.py`, never inferred from the database) and, per run:
fetches that run's persisted feature vectors for the requested feature set/version, resolves
each vector's label from that run's ground-truth timeline (point-in-time: only a
ground-truth tick at or before the vector's `as_of_timestamp`, within a staleness bound, is
ever used — see `GroundTruthTimeline.label_at_or_before`), and drops the sample entirely if
no usable label exists (covers `NETWORK_FAILURE`-only ticks). The result is a
`DatasetManifest` (versioned, with a leakage audit) plus a list of `DatasetSample`.

## Splitting — grouped by run, time-ordered, stratified by label

Naive random-row splitting is never used (`ml_service.datasets.splitting`). Splits are
assigned at the RUN level. `assign_run_splits` sorts all runs by their own start timestamp
and sends the earliest ~60% to TRAIN, the next ~20% to VALIDATION, and the rest to TEST.

`build_dataset.py` actually calls `assign_stratified_run_splits`, which applies that same
time-ordered 60/20/20 logic *independently within each label's own group of runs*, not once
globally. A first real training run on the plain global split (`assign_run_splits`) exposed
why this matters at this dataset's scale: two of the eight labels
(`INDEPENDENT_BEARING_ISSUE`, `UNKNOWN`) happened to have every one of their runs fall after
the global 60% cut point, so TRAIN contained zero examples of either — not a hard label, an
unlearnable one (classifier macro F1 ≈ 0.05). Under stratification, a label with one run
goes entirely to TRAIN (there is no way to hold out a run for TEST without making it
unlearnable); a label with two runs goes one to TRAIN and one to TEST, skipping VALIDATION
entirely (VALIDATION only matters for the anomaly model's NORMAL-only threshold calibration
— a rare label having zero VALIDATION rows costs nothing, whereas zero TEST rows would hide
it from every per-class TEST metric); three or more runs use the standard proportional
split. `force_test_run_ids` (the second, otherwise-unseen asset's runs; the sole
multi-fault-composition run; the sole connectivity-loss run) is applied on top of either
function, always landing in TEST regardless of timestamp or group.

Every sample from one run is then assigned that run's split (`verify_no_run_crosses_splits`
proves no run ever appears in two splits, independent of which split function produced the
assignment). `run_id` is used ONLY for this grouping — `DatasetSample.run_id` is a separate
struct field from `feature_values` and is never copied into it.

## Leakage audit

`ml_service.datasets.leakage_audit` runs two independent checks on every dataset build:

1. `audit_feature_names` — scans the feature-name list for scenario/ground-truth vocabulary
   (`scenario`, `severity`, `ground_truth`, `fault_start`, `run_id`, `future_duration`,
   `failure_phase`, `true_value`). Structural proof, run every build, not an assumption.
2. `audit_proxy_leakage` — flags any discrete (non-continuous-float) feature whose observed
   value predicts a single label class with >=98% purity and >=5 supporting samples — the
   concrete shape a run-identity artifact accidentally leaking into a feature would take.

Both results are recorded in the persisted `DatasetManifest`.

## Model-specific feature selection

`ml_service.training.feature_sets` documents, per model, which Phase 10 features are
excluded and why:

- `context.machine_type`, `context.criticality`, `context.firmware_version`,
  `context.controller_version` — excluded everywhere: with a small demo fleet these would
  trivially encode "which machine" (defeating the asset-generalization test) or act as a
  fine-grained run/config identifier.
- `rules.*` (Phase 9 rule-evidence features) — excluded from both models. Four of them
  (`rules.restriction_pattern_active`, `rules.leakage_pattern_active`, `rules.
  pump_degradation_pattern_active`, `rules.bearing_condition_pattern_active`) are Phase 9's
  own deterministic detectors for the same failure modes the classifier predicts; training
  on them would make the classifier largely reproduce the rules engine instead of learning
  independent evidence from raw signals, working against CLAUDE.md's "combine rules AND ML
  as independent evidence sources."
- The anomaly model additionally excludes small-cardinality categorical CONTEXT features
  (`context.operating_state`, `.load_bucket`, `.rpm_bucket`, `.cycle_phase`, `.
  sensor_availability_mask`) — Isolation Forest has no native categorical handling, and this
  model is meant to catch multivariate numeric deviation. The classifier keeps them
  (one-hot encoded) since they are physically meaningful and not identifiers.

## Missing values and preprocessing

`ml_service.training.preprocessing.Preprocessor` is fit on TRAIN only. Numeric/boolean
features: median imputation (median computed from TRAIN's observed values only) plus an
explicit `<feature>.__missing__` indicator column — matching Phase 10's own rule that an
observed zero is never confused with "missing." Small-cardinality categorical features:
one-hot against a TRAIN-fit vocabulary, with explicit `__OTHER__` (unseen category) and
`__MISSING__` buckets, so an inference-time value never crashes or is silently dropped. The
fitted `Preprocessor` (medians/means/stddevs/vocabularies/final column order) is persisted
inside the model artifact and reused unchanged at inference — train/serve parity by
construction, not by convention.

## Models

### Anomaly — Isolation Forest

`ml_service.models.anomaly.AnomalyModelArtifact` wraps `sklearn.ensemble.IsolationForest`.
Trained on TRAIN samples labeled `NORMAL` only (`n_estimators`/`contamination` from
`config/anomaly_v1.yaml`, contamination deliberately small and non-zero — trusted "healthy"
data still contains ordinary sensor noise/borderline operating states, so a strictly-zero
contamination would bias the model's internal offset; this is unrelated to how the actual
operating threshold is chosen). See ADR (Isolation Forest choice) in
`TECHNICAL_DECISIONS.md`.

### Classifier — baseline + primary

`ml_service.models.classifier.ClassifierModelArtifact` wraps a scikit-learn classifier
behind one shared contract. Two are trained on the identical TRAIN split/preprocessing:

- **Baseline**: `LogisticRegression` (`class_weight="balanced"`) — the real, honest floor
  the primary model must beat or justify itself against (Phase 11 brief §16, §50).
- **Primary**: `HistGradientBoostingClassifier` — chosen over XGBoost for a clean CPU-only
  integration with no extra native dependency in an already scikit-learn-based service,
  native missing-value support, and strong tabular performance at this dataset's scale. See
  ADR (classifier choice) in `TECHNICAL_DECISIONS.md`.

Class imbalance: `compute_sample_weight("balanced", y)` for the primary model,
`class_weight="balanced"` for the baseline — a deliberate, inspectable strategy, not SMOTE
(this dataset has real temporal/run structure SMOTE's synthetic interpolation would not
respect).

## Threshold selection (validation only, never test)

Anomaly: the operating `anomaly_score` threshold is the score at the
`target_validation_fpr` percentile of VALIDATION's `NORMAL`-labeled samples' scores
(`np.quantile`). Classifier: `unknown_confidence_threshold` and the `MODERATE`/`HIGH`
confidence-category boundaries are config values (`classifier_v1.yaml`), chosen by
inspecting VALIDATION-split probability distributions during development — never read from
or fit against TEST. `docs/results/model_evaluation.json` records the exact values used.

## UNKNOWN / INSUFFICIENT_FEATURES handling

Two independent "the model should not force an answer" paths, both structural:

- **INSUFFICIENT_FEATURES** — `InferenceService` checks each model's
  `minimum_required_features` before ever calling the model; if any are missing, it returns
  a structured `INSUFFICIENT_FEATURES` result with no score/prediction at all.
- **UNKNOWN** — even with enough features, if the classifier's top class probability is
  below `unknown_confidence_threshold`, `ClassifierModelArtifact.predict_label` returns
  `FailureLabel.UNKNOWN` rather than the highest (but low-confidence) known class.

## Explainability

`ml_service.explainability.explain`:

- Tree-model global importance: `estimator.feature_importances_`.
- Per-prediction classifier attribution: feature ablation (zero one active feature at a
  time, measure the resulting class-probability shift) — a deliberate choice over SHAP to
  avoid a heavyweight dependency for a CPU-only demo-scale service; documented as a
  heuristic, not exact attribution.
- Anomaly per-prediction attribution: rank features by `|z-score|` against the TRAIN
  distribution the preprocessor was fit on — the "safe heuristic" Phase 11 brief §37
  explicitly allows when exact attribution (Isolation Forest has none, natively) is
  unavailable.

Every explanation is phrased "features contributing most to this prediction," never
"caused" — enforced by the module's own docstring contract and tested
(`test_explain_classification_prediction_returns_no_causal_language_fields`).

## Model registry and lifecycle

`ml_service.registry.registry.ModelRegistry` is filesystem-based
(`artifacts/models/{model_id}/{version}/{model.joblib,metadata.json}`), indexed by
`artifacts/models/registry_index.json` — every lookup goes through that index (or an
explicit `(model_id, version)`), never "newest file in the folder." Lifecycle:
`EXPERIMENT -> VALIDATED -> STAGING -> PRODUCTION -> RETIRED`; Phase 11's training CLIs only
ever assign `EXPERIMENT` or `VALIDATED` (a documented, code-visible gate per model — see
each `train_*.py` module) — promotion to `STAGING`/`PRODUCTION` is out of scope (MLOps
workflow, later phase).

## Inference service

`ml_service.inference.service.InferenceService` loads an explicit `(model_id,
model_version)` through the registry, requires `status` to be `VALIDATED`/`STAGING`/
`PRODUCTION` (raises `ModelNotServableError` otherwise — an `EXPERIMENT` model is never
served), applies the minimum-feature check, and returns `AnomalyInferenceResult` /
`ClassificationInferenceResult`. Deterministic for identical input
(`test_classification_is_deterministic_for_same_input`).

## Backend integration

- `app.domain.models.MLInferenceResult` (migration `db57458c6150`) — one table, both result
  kinds (`ANOMALY`/`CLASSIFICATION`), append-only.
- `app.ml.services.ml_inference_service.MLInferenceOrchestrationService` — computes the
  current Phase 10 feature vector via the unchanged `FeatureEngine`, runs `ml-service`
  inference, persists the result. The only backend module that imports `ml_service`.
- API (`app.api.v1.ml`, tenant-scoped): `GET /api/v1/ml/machines/{id}/latest?model_id=...`
  (compute + persist + return), `GET /api/v1/ml/machines/{id}/history`, `GET
  /api/v1/ml/models`, `GET /api/v1/ml/models/{model_id}`.
- `app.ml.registry.get_model_registry()` — the one place the backend builds a
  `ModelRegistry`, pointed at `Settings.ml_artifacts_dir` (`ML_ARTIFACTS_DIR`, default
  `../ml-service/artifacts/models` for local host runs). In Docker Compose, `backend`
  bind-mounts the host's `ml-service/artifacts/models` **read-only** into the container at
  that path (ADR-101) — the registry a training run produces on the host is what the
  container reads; nothing is copied into the image and the container never writes to it.

## Fallback behavior

If no VALIDATED model is registered, or a registered model raises,
`MLInferenceOrchestrationService` raises `MLModelNotAvailableError` and the API returns
`503` — the rest of the platform (telemetry, quality, baselines, rules) is completely
unaffected, matching LOOP.md "Failure Handling": "If ML is unavailable: rules must
continue." No backend code path requires ML to be present.

## Dataset generation (how the reference dataset was actually produced)

`edge/scripts/generate_ml_training_data.py` drives real `SimulationEngine` scenario runs
through the real Phase 5 edge acquisition adapter, the real MQTT broker, and the real Phase
6 bridge/consumer into the real TimescaleDB `telemetry` table — the same harness Phase 7/9's
`run_scenario_validation.py`/`run_rules_validation.py` already established, extended to
also capture each tick's `GroundTruthRecord` to a local JSONL file (never round-tripped
through the wire). The always-on Phase 7/8/9/10 workers (data-quality, baseline, rules,
feature) process the resulting telemetry exactly as they do for any other traffic.

**Non-overlapping simulated time slots.** `SimulatorTelemetrySource` anchors a run at real
wall-clock "now" by default; running many scenarios back-to-back on the same machine would
otherwise give every run near-identical simulated timestamps, silently blending unrelated
scenario runs' readings into the same feature-computation window. The generator instead
builds `SimulationEngine` directly with an explicit `start_time`, offsetting each run by
`RUN_SLOT_HOURS` (8h, comfortably more than one run's own 6h duration) so every run's
`[start, end)` window is disjoint from every other's on the same machine — a correctness
requirement discovered and fixed during this phase's own live verification (see
`TECHNICAL_DECISIONS.md`, ADR: dataset generation time-slot isolation).

`python -m app.features.materialize` (unchanged Phase 10 CLI) then backfills feature vectors
for each run's exact time window, and `DatasetBuilder` assembles the final dataset from
those persisted vectors plus the captured ground truth.

## Limitations

- Reference dataset scale is deliberately modest (bounded run count/duration, i7/16GB
  development-machine budget) — see `docs/MODEL_CARD.md` for exact counts and what that
  implies for statistical confidence in the reported metrics.
- Single-label classifier; multi-fault ticks are labeled by the highest-severity active
  scenario only (see "Ground truth" above).
- `OVER_LUBRICATION`/`LOW_RESERVOIR` map to `UNKNOWN` rather than being learned as distinct
  classes (label schema is fixed at 8 classes by the Phase 11 brief).
- No periodic/scheduled inference worker in Phase 11 — inference is computed on demand by
  the `/latest` API call (mirrors Phase 10's own `/features/.../latest` pattern) and
  persisted for `/history` to read; a periodic ml-worker is an explicit non-goal here
  (MLOps workflow, later phase).
- Ablation-based explainability is a heuristic, not exact Shapley attribution.
