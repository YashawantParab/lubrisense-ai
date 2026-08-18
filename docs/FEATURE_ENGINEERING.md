# Feature Engineering — Phase 10

Status: COMPLETE (Phase 10 implementation; verification record in `IMPLEMENTATION_STATUS.md`)

## Purpose

The feature layer turns trusted telemetry, ACTIVE contextual baselines, observed cycle
behavior, rule evidence, and asset context into versioned point-in-time model inputs. It
does not train or run an ML model, estimate hidden state, diagnose a condition, or recommend
maintenance work.

**NO SIMULATOR GROUND TRUTH IS USED IN FEATURES.** The package imports no simulator or
scenario type. Scenario ground truth may be consulted only after vectors exist to validate
qualitative behavior.

## Architecture

```
backend/app/features/
  domain/            immutable definitions, input snapshots, vector contract
  definitions/       registry catalog and four versioned feature sets
  config/            validated demo feature policy
  services/          shared computation engine and tenant-scoped query service
  repositories/      bulk source reads and idempotent vector persistence
  materialization/   selected-vector persistence boundary
  workers/           periodic latest-vector materializer
  materialize.py     deterministic historical CLI
```

`FeatureEngine.compute()` is the only feature-computation orchestrator. Online latest
computation, historical materialization, the periodic worker, and tests all call this same
method. `services/computation.py` contains database-free feature math over immutable input
snapshots. There is no offline-only or online-only feature formula.

## Allowed Sources

- Phase 6 `telemetry`, including hierarchy context and source timestamps
- Phase 7 `sensor_quality_state` eligibility and quality-issue evidence
- Phase 8 `baseline_profile` rows in `ACTIVE` state only
- Phase 9 rule findings as evidence features only
- registered sensor availability and machine type/criticality
- observed operating state, firmware, and controller/config versions

Forbidden sources include simulator `true_value`, hidden physical/cycle state, scenario
type/severity/target, scenario ground truth, technician outcomes, future maintenance, and
future telemetry.

## Quality Gating

Numeric equipment features require both:

1. sensor eligibility `ELIGIBLE` or `ELIGIBLE_WITH_CAUTION`; and
2. per-reading `Telemetry.quality == GOOD` with a non-null value.

`ELIGIBLE_WITH_CAUTION` is included and exposed in `quality.caution_fraction.15m` and the
vector quality summary. `INELIGIBLE`, missing, communication-loss, unavailable, and other
non-GOOD readings do not enter numeric equipment aggregates. They remain visible through
quality and missingness features. An untracked sensor has no eligibility evidence and is
treated as ineligible, not trusted by default.

No code path substitutes zero for missing telemetry. A legitimate observed zero remains a
zero; an absent or suppressed feature is omitted from `feature_values` and named in
`missing_features`.

## Event-Time Windows and Point-in-Time Correctness

All physical windows use `Telemetry.source_timestamp`. `persisted_timestamp` and arrival
timestamps never select physical samples. Arrival timing is used only to calculate the
explicit `quality.late_fraction.15m` confidence feature.

For an as-of timestamp T, the source repository enforces:

```
T - maximum_lookback <= source_timestamp <= T
```

ACTIVE baselines with a physical `window_end` after T are excluded. Rule findings must have
been activated by T and not resolved before T. The engine rejects a supplied context that
contains a future telemetry point. The controlled leakage test inserts a row after T and
proves recomputation at T remains identical.

## Feature Groups

- current state: latest trusted observations for registered measurement types
- rolling statistical: compact median/mean/stddev/MAD/quantile/range/count selections
- baseline deviation: delta, guarded ratio, robust MAD distance, percentage deviation
- trend/rate: bounded robust pairwise slope, first/relative difference, timestamped rate
- cycle: observable pressure segmentation, flow integration, duration/rise/peak/success
- cross-signal: physically interpretable guarded ratios and relative changes
- temporal: elapsed deviation duration and consecutive deviating cycles
- quality: trusted/caution/missing/late fractions and recent issue evidence
- context: explicit categories, versions, and sensor availability mask
- rule evidence: ACTIVE finding indicators and ordinal evidence strength, not diagnoses

The authoritative list is `docs/FEATURE_CATALOG.md`, generated from the runtime registry.

## Baseline Use

Only `BaselineState.ACTIVE` profiles are loaded. Resolution priority is matching contextual
baseline, sensor-level rolling baseline, then static engineering reference. Every resolved
feature records `profile_id`, source `sensor_id`, lineage version, config version, and
fallback source in `baseline_versions`. On machines with multiple same-type sensors, the
baseline must belong to the sensor that supplied the selected current observation. Candidate,
BUILDING, STALE, INVALIDATED, and SUPERSEDED rows are never consumed.

Relative and percentage features return missing when the baseline denominator is absent or
within the configured epsilon. Robust deviation returns missing when no usable spread is
available; it does not invent infinity or zero distance.

## Cycle Semantics

Cycles are reconstructed only from observed pressure runs above the policy-configured idle
threshold. Flow volume uses event-time trapezoidal integration per sensor. Completion,
failure, and time-since-success require observed `CYCLE_COMPLETION`. Pump runtime uses an
observed runtime-counter delta where available, with a pressure-cycle/current-presence
proxy otherwise. None of the simulator's internal five-state cycle machine is visible.

## Registry and Feature Sets

Every `FeatureDefinition` declares stable name, semantic version, group, type, unit, entity
scope, source measurements, window, aggregation, context requirements, quality requirement,
null behavior, owner, availability, status, description, and feature-set membership.

Initial sets:

- `LUBRICATION_ANOMALY_V1`: future unsupervised anomaly detection
- `FAILURE_CLASSIFICATION_V1`: future supervised observable-pattern classification
- `REFILL_FORECAST_V1`: future depletion/refill forecasting
- `STATE_ESTIMATION_V1`: future state-estimation input

Definitions began at `1.0.0`; temporal run and baseline-deviation definitions are `1.0.1`
after event-order and same-type-sensor provenance corrections found during live validation.
`LUBRICATION_ANOMALY_V1` and `FAILURE_CLASSIFICATION_V1` are therefore set version `1.0.2`;
the other initial sets are `1.0.1`. Semantic changes require a definition version bump, and
membership or contract changes require a feature-set version bump.

## Feature Vector Contract

`FeatureVector` contains deterministic vector id, set name/version, tenant, machine,
optional component, as-of time, values, explicit missing list, quality summary, source
window, baseline/rule/definition versions, feature-policy version, and creation time.
Vectors are tenant-scoped by composite database foreign keys.

## Storage and Materialization

The strategy is hybrid:

- online latest vectors are computed on demand without a write;
- historical/training snapshots and periodic validation snapshots are materialized;
- trivial intermediate statistics are not persisted separately.

The logical key is `(tenant, machine, entity_key, feature_set, feature_set_version,
as_of_timestamp)`. A deterministic UUID and `uq_feature_vector_logical` both enforce
idempotency. Conflict handling is `DO NOTHING`; historical vectors are never silently
overwritten.

Historical CLI:

```
python -m app.features.materialize \
  --machine-id <uuid> \
  --feature-set LUBRICATION_ANOMALY_V1 \
  --start 2026-08-18T00:00:00Z \
  --end 2026-08-18T06:00:00Z \
  --interval-seconds 900
```

The CLI reports actual vectors requested/inserted, rows scanned, features generated, and
duration. It uses the same engine as the online service.

## API and Validation UI

- `GET /api/v1/features/machines/{machine_id}/latest`
- `GET /api/v1/features/machines/{machine_id}`
- `GET /api/v1/features/vectors/{vector_id}`
- `GET /api/v1/features/registry`
- `GET /api/v1/features/sets`

All require the tenant context. `/features` is a minimal developer view for selecting a
machine/set and inspecting values, missingness, quality, source window, and provenance.

## Observability and Health

The periodic worker exposes `/health`, `/ready`, and `/metrics` on port 8086. Readiness
depends on PostgreSQL. Metrics include `feature_vectors_computed`,
`feature_computation_failures`, `feature_computation_duration_seconds`, `features_missing`,
`features_suppressed_quality`, `feature_materialization_lag_seconds`, and rows scanned.

## Unit Handling

Units live on every numeric definition: raw engineering unit, explicit compound slope/rate
unit, seconds for duration, count for counts, fraction/percent where appropriate, and
dimensionless for ratios. The registry API and feature catalog preserve these semantics.

## Limitations

- Vectors are machine-scoped in v1; `component_id` is reserved for later component sets.
- Registered same-type sensors are aggregated at machine scope; bearing-specific feature
  vectors can be added as a new set/version without changing current contracts.
- Historical eligibility uses Phase 7's current sensor eligibility because Phase 7 does not
  persist a complete point-in-time eligibility timeline. Per-reading quality and strict
  source-time filtering still apply; this inherited limitation is explicit, never hidden.
- ACTIVE baseline rows may be refined in place by Phase 8. Exact reconstruction of a
  previously refined ACTIVE snapshot would require immutable baseline snapshots per refresh.
- Cycle reconstruction is intentionally observable and coarser than controller hidden state.
  A pressure cycle needs at least two eligible observations above the idle threshold; coarse
  sampling can therefore leave cycle features explicitly missing even when one pressure peak
  is visible.
- Categorical features are explicit strings/buckets; Phase 10 fits no encoders or embeddings.
- All thresholds in `demo_feature_policy.yaml` are synthetic demo assumptions.
