# System Testing (Phase 35)

## Purpose

Test the platform as a system, not just as isolated packages — re-running every real
verification script this project already has against the live Docker stack, running the
full package-level regression suites, and finding/fixing what a purely unit-level test
suite structurally cannot catch (a real Postgres `ON CONFLICT` planner error, a real
structured-logging gap).

## Full regression (all packages)

| Package | Result |
|---|---|
| backend | 680/680 passing (`uv run pytest`) |
| ml-service | 69/69 passing |
| simulator | 139/139 passing (against a real seeded Postgres) |
| edge | 69/69 passing (against real Postgres + Mosquitto) |

`ruff`/`mypy` clean on every package. All four are also exercised in
`.github/workflows/ci.yml` (Phase 34).

## End-to-end data path verification

Every real verification script in `scripts/` was re-run against the live Docker stack
(not just described) as part of this phase:

- `verify_pipeline.sh` — round trip, duplicate delivery, unsupported schema, unknown
  sensor, Kafka outage (buffer + drain), database outage (retry without loss/dup) — **all
  PASS**
- `verify_mqtt.sh`, `verify_kafka.sh` — **PASS**
- `verify_baselines.sh` — static/rolling baseline activation, contextual-profile
  differentiation, idempotency, live API parity — **all PASS**
- `verify_rules.sh` — contextual-baseline rules, generic degradation pattern, reservoir
  rule, explainability, idempotency, live API parity — **all PASS**
- `verify_data_quality.sh` — all 11 synthetic cases (sequence gap through stuck sensor)
  — **all PASS** (case 11 required the two real fixes below)
- `edge/scripts/run_scenario_validation.py` — SENSOR_DRIFT, SENSOR_DROPOUT **PASS**;
  NETWORK_FAILURE **fails** in this shared long-lived environment for the same
  already-documented reason as the pre-existing SENSOR_DRIFT timing note (see "Known
  limitations" below) — not a new regression
- `ml-service/scripts/verify_ml_pipeline.py` — reports no VALIDATED model for either
  production-facing model ID, exactly matching `docs/MODEL_CARD.md`'s and
  `docs/MLOPS.md`'s already-documented, honest state (neither model cleared its
  promotion gate) — not a regression

## Two real bugs found and fixed this phase

1. **Structured logging silently dropped `extra=` fields** (ADR-167) — every
   `logger.warning(msg, extra={...})` call site across `app/pipeline/`,
   `app/data_quality/`, `app/main.py` had its diagnostic payload discarded by
   `JSONLogFormatter`/`ConsoleLogFormatter` since the logging foundation was first built.
   Fixed; 5 new tests in `tests/test_logging.py`.
2. **Every window-scoped data-quality issue upsert failed silently** (ADR-168) —
   `QualityIssueRepository.upsert_active_window_issue()`'s `ON CONFLICT ... WHERE status
   IN (...)` used a bind-parameterized predicate, which Postgres cannot match against a
   partial unique index (must be a literal/constant-foldable expression). This had been
   failing on every call since Phase 7, invisible until bug #1 was fixed and the real
   error became visible in logs. Fixed; 2 new tests in
   `tests/data_quality/test_quality_issue_repository.py`; re-verified live via
   `verify_data_quality.sh` (all 11 cases now pass, previously case 11 failed).

Fixing bug #2 required rebuilding **every** worker container (`backend`,
`mqtt-bridge`, `telemetry-consumer`, `data-quality-worker`, `baseline-worker`,
`rules-worker`, `feature-worker`), not just `data-quality-worker` — each is a
separately-tagged image built from the same `backend/Dockerfile`, so rebuilding one does
not refresh a sibling's image even though they share source code.

## Required scenario matrix

The ten scenario types named in the Phase 35 brief (healthy, gradual restriction, sudden
blockage, leakage, pump degradation, low reservoir, independent bearing issue, sensor
drift, sensor dropout, network outage) plus multi-fault are already exercised by the real
Phase 11 ML training-data generation run (`edge/scripts/generate_ml_training_data.py`,
documented in `docs/MODEL_CARD.md`) — each scenario type has a real, persisted simulator
run and ground-truth file, with honestly-reported per-scenario detection rates in
`docs/results/model_evaluation.json` (re-verified reproducible in Phase 32). This phase
did not re-run all ~20 six-simulated-hour scenario runs from scratch (a multi-hour
undertaking); it re-verified the fast, targeted, real-stack scripts above instead,
consistent with this project's established practice of not re-running the full historical
simulation suite on every phase.

## Safety validation

Already covered by the extensive Phase 24 (Security/RBAC), Phase 19 (agent guardrails),
and Phase 25 (audit) test suites, all included in the 680-test backend regression above:
no-machine-control (agent tool allowlist), tenant isolation, RBAC, draft-vs-action
boundary, no-auto-retraining/no-auto-promotion (re-confirmed directly in Phase 32).

## Resilience validation

`verify_pipeline.sh`'s Kafka-outage and database-outage cases (above) are real,
re-executed proof, not a description. ML/state-estimator/RAG/LLM/CMMS unavailability
degradation is covered by the existing Phase 27 resilience test suite (part of the 680).

## Data integrity

`verify_pipeline.sh` proves idempotency/deduplication directly (duplicate delivery →
exactly one row); `verify_baselines.sh`/`verify_rules.sh` prove idempotency for their own
write paths (repeated backfill/reprocess → no duplicate version/row). Audit immutability
and cross-tenant constraints are covered by the existing Phase 24/25 test suites.

## Browser testing

Primary routes (Overview, Fleet, Incidents, Metrics, System Status, machine detail) were
walked through live against the rebuilt Docker stack this phase — all rendered correctly
with real data, honest empty states where applicable (Metrics: "Not enough data" /
"value is undefined, not zero" for a tenant with no feedback yet), no console errors. The
full 20-step flagship walkthrough (Phase 39's own checklist) is performed as part of
Phase 36/39, not duplicated here.

## Known limitations

- `run_scenario_validation.py`'s NETWORK_FAILURE case fails in this specific
  long-lived, heavily-reused local demo environment for the same class of reason already
  documented for Phase 7's SENSOR_DRIFT case: the scenario's simulated `source_timestamp`s
  run ahead of real wall-clock time within the script's compressed real-time execution,
  and `WindowEvaluator.evaluate_machine_communication()` queries against real
  `datetime.now(UTC)` — so freshly-injected telemetry can fall outside the query's
  window at evaluation time. Not fixed (would mean either loosening the script's timing
  or changing the evaluator to accept simulated time, both bigger changes than this
  phase's scope); documented honestly rather than silently retried until green.
- `WindowEvaluator.evaluate_machine_communication()` has a related, real edge case not
  fixed this phase: if a machine's tracked sensors produce **zero** telemetry rows in the
  entire 5-minute lookback window (not just a gap within a window that has some points),
  `representative_sensor_id` is `None` and the function returns without recording any
  `COMMUNICATION_LOSS` issue — arguably the clearest case of communication loss goes
  unflagged. Left as a known limitation rather than fixed under time pressure in this
  already-large phase; a real fix would need a way to record the issue without a
  "representative sensor" (e.g. against the last-known sensor, or a machine-level-only
  issue row) — a small design decision worth its own review, not a one-line patch.
