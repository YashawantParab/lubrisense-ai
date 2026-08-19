# MLOps (Phase 32)

## Purpose

Phase 11 built the model registry, dataset manifests, and reproducible training scripts.
This phase hardens that foundation into an operationally governed lifecycle: an integrity
check on every loaded artifact, an explicit human-controlled promotion path, honest model
comparison, feedback provenance tracking, and reference-scoped drift/coverage checks. No
part of this phase introduces automatic retraining or automatic promotion — both remain
explicitly forbidden by CLAUDE.md and by ADR-009.

## Model registry hardening

`ml_service.registry.ModelRegistry` now computes a sha256 checksum of every artifact at
registration time (`ModelMetadata.artifact_checksum`) and verifies it on every `load()`
call by default, raising `ArtifactIntegrityError` on a mismatch (e.g. an out-of-band file
replacement) rather than silently loading a different model than the one recorded.
`verify_checksum=False` remains available for forensic inspection of a known-corrupted
artifact. See `tests/test_registry.py`.

## Model metadata

`ModelMetadata` already carried model_id/version/type, dataset_id/version, feature_set/
version, hyperparameters, metrics, thresholds, seed, code_version, status, and
limitations since Phase 11 — the only genuinely missing field was `artifact_checksum`,
added this phase.

## Dataset manifest

`DatasetManifest` (Phase 11) already records source assets, source scenarios, time
range, seeds, feature list, split strategy/counts, label schema version, code version,
and a leakage audit result — unchanged this phase; see `docs/ML_ARCHITECTURE.md`.

## Training reproducibility

Unchanged, re-verified this phase: `uv run python -m ml_service.training.train_anomaly
--dataset-dir ...` and `train_classifier` were re-run against the existing dataset
directories and produced byte-for-byte identical metrics to the prior training run
(same macro F1, same PR-AUC, same detection rates) — real evidence the pipeline is
reproducible, not merely documented as such.

## Model promotion

`scripts/promote_model.py` is now the **only** supported way to move a model version
between lifecycle stages beyond EXPERIMENT/VALIDATED (which training scripts decide).
It:

- requires an explicit `--reason` and `--actor`
- refuses to skip a stage (EXPERIMENT -> STAGING directly is refused; must pass through
  VALIDATED)
- appends every decision — including a snapshot of the model's metrics at decision time
  — to `artifacts/models/promotion_log.jsonl` (append-only, never rewritten)

Demonstrated live this phase:

- **Refused**: `FAILURE_CLASSIFICATION_V1@1.0.0` (EXPERIMENT) → PRODUCTION was refused
  for skipping stages, logging nothing.
- **Accepted**: `FAILURE_CLASSIFICATION_BASELINE_V1@1.0.0` (VALIDATED) → STAGING was
  promoted with an honest reason citing its real measured advantage over the primary
  classifier. See `artifacts/models/promotion_log.jsonl` for the recorded decision.

Neither `LUBRICATION_ANOMALY_V1@1.0.0` nor `FAILURE_CLASSIFICATION_V1@1.0.0` — the two
model IDs the backend `/ml` API actually exposes — have been promoted past EXPERIMENT.
This is not an oversight: `LUBRICATION_ANOMALY_V1`'s calibrated threshold produces a
higher false-positive rate on TEST than its gate allows, and `FAILURE_CLASSIFICATION_V1`
does not beat its own baseline (`primary_beats_baseline: false` in
`artifacts/evaluation/classifier_evaluation.json`). Promoting either without a real
metrics justification would violate CLAUDE.md's "do not fabricate" principle; both stay
honestly at EXPERIMENT, and `InferenceService` correctly refuses to serve them.

## Model comparison

`scripts/compare_models.py` compares two registered versions on: status, model type,
artifact size, artifact checksum, measured inference latency (a real timed
`predict_proba` call over real TEST samples from the model's own dataset directory, for
classifier models), test macro/weighted F1, and per-class recall, all read verbatim from
the registry — nothing recomputed or estimated. Example: comparing
`FAILURE_CLASSIFICATION_BASELINE_V1` vs. `FAILURE_CLASSIFICATION_V1` shows the baseline
ahead on every axis (macro F1 0.286 vs. 0.147; every per-class recall equal or higher) —
reported exactly as measured, weak performance not hidden.

## Feedback provenance

`scripts/export_feedback_provenance.py` (backend) is a **read-only** report joining every
`FeedbackRecord` (Phase 17) to the `ConditionAssessment` it was recorded against, and
from there to the `ml_result_ids`/`rule_finding_ids`/`state_estimate_ids` that assessment
cited as evidence. This is the provenance chain a future, explicitly human-triggered
retraining dataset build would need — the script does not build, queue, or trigger any
retraining itself. Verified live against the real database and covered by
`tests/test_export_feedback_provenance.py`.

## Drift / coverage monitoring (reference implementation)

`ml_service.monitoring.drift` computes a Population Stability Index (PSI) per numeric
feature between a reference batch and a current batch, plus per-feature missingness
delta and overall instrumentation coverage — `scripts/check_drift.py` runs it against a
dataset's own TRAIN (reference) vs. TEST (current) split, or two separate dataset
directories.

**This is explicitly not a production drift-detection system**: there is no scheduler,
no alerting integration, no persisted score history over time, and no automatic action
on a drift finding — consistent with this platform's no-auto-retraining rule. Verified
live against `data/datasets/FAILURE_CLASSIFICATION_V1`: TRAIN vs. TEST correctly flags
`SUBSTANTIAL_SHIFT` on ten features (expected, since TEST is deliberately forced to
include the second independent asset's runs, the multi-fault run, and the
network-failure run — see `docs/ML_ARCHITECTURE.md` "Splitting").

## Model card

See `docs/MODEL_CARD.md` — already accurate and current as of this phase; only the
"MLOps tooling" cross-references were added.

## Known limitations

- The promotion log is a local JSONL file, not a database table — sufficient for a
  reference implementation, not for a multi-operator production environment where
  concurrent writes would need real locking.
- Drift PSI requires at least 20 reference and 10 current samples per feature to compute
  a bucketed score; smaller batches report `psi: null` honestly rather than a misleading
  number.
- No feature-store integration — drift checks operate on already-built dataset
  directories, not a live streaming feature pipeline.
