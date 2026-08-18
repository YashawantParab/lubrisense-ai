# Data Quality Engine — Phase 7 Implementation

Status: PHASE 7 — DRAFT FOR ACCEPTANCE
Last updated: 2026-08-18

This document describes the data-quality engine delivered in Phase 7: a structured,
versioned, explainable assessment of whether telemetry can be trusted, computed
independently of and prior to any future baseline/rule/ML/Kalman/condition-intelligence
consumer (Phase 8+). It builds directly on Phase 6's central pipeline
(`docs/TELEMETRY_PIPELINE.md`) — it does not replace or duplicate Phase 6's structural
validation, it adds a second, separate layer of judgment about telemetry that Phase 6
already accepted.

Phase 7 is data quality only. It does **not** implement baselines, a rules engine, feature
engineering, ML, Kalman filtering, condition/decision intelligence, incidents, RAG, agents,
CMMS, or the final product UI — see `IMPLEMENTATION_STATUS.md` for the phase boundary.

---

## 1. Why a separate layer

Phase 6 answers "is this event structurally valid and attributable to a real tenant/
sensor/machine" — anything that parses and resolves is persisted as-is, with no judgment
about whether the *value* is trustworthy. A sensor can be stuck, drifting, late, out of
range, or intermittently silent while still producing perfectly well-formed events. Phase 8+
intelligence must never silently treat a stuck or drifting reading the same as a healthy
one — so Phase 7 exists to make that judgment explicit, structured, and versioned *before*
any of that later intelligence exists to consume it.

Three distinct things are deliberately kept separate and never conflated:

- **Raw telemetry** (`telemetry`, Phase 6) — never modified by Phase 7.
- **Data quality assessment** (`quality_assessment`, `quality_issue`, `sensor_quality_state`
  — this document) — a judgment *about* a raw event/window, not a replacement for it.
- **Clean/eligible input** — a downstream *consumption decision* (Phase 8+ reads
  `sensor_quality_state.eligibility` before trusting a reading), not a separate table of
  "corrected" values. Phase 7 never fabricates or substitutes a value.

---

## 2. End-to-end data flow

```
Simulator --> Edge --> MQTT --> MQTT-Kafka Bridge --> Kafka (lubrisense.telemetry.v1)
                                                              |
                              +-------------------------------+-------------------------------+
                              |                                                               |
                    Telemetry Consumer (Phase 6)                              Data Quality Worker (Phase 7)
                    group: lubrisense-telemetry-consumer                      group: lubrisense-data-quality
                              |                                                               |
                              v                                                               v
                    TimescaleDB `telemetry`                          QualityEngine (event-level, synchronous per batch)
                                                                      WindowEvaluator (window-level, periodic asyncio task)
                                                                               |
                                                                               v
                                              quality_assessment / quality_issue / sensor_quality_state
                                                                               |
                                                                               v
                                                        Data Quality API  -->  /data-quality frontend view
```

The data-quality worker is a **second, independent Kafka consumer group** reading the exact
same `lubrisense.telemetry.v1` topic Phase 6's consumer reads — Kafka fan-out, not a
post-persistence trigger, not a shared transaction with Phase 6's insert. Quality-worker
failure or lag never blocks or slows telemetry ingestion, and Phase 6's consumer never knows
Phase 7 exists (ADR: worker architecture, `TECHNICAL_DECISIONS.md`).

An event that Phase 6 itself rejects (unsupported schema version, unknown sensor, context
conflict — routed to `telemetry_quarantine`) never gets a quality assessment either: the
quality worker independently re-runs the same structural validation and enrichment Phase 6
uses, and simply skips anything that wouldn't have been accepted into `telemetry` in the
first place. There is nothing valid to assess quality for.

---

## 3. Quality dimensions

Every rule belongs to exactly one dimension (`app.domain.enums.QualityDimension`):

| Dimension | Question | Example issue types |
|---|---|---|
| COMPLETENESS | Is data missing? | `MISSING_VALUE`, `SEQUENCE_GAP` |
| VALIDITY | Is the value itself sound? | `OUT_OF_RANGE`, `INVALID_VALUE`, `UNIT_MISMATCH` |
| TIMELINESS | Did it arrive on time? | `LATE_ARRIVAL`, `VERY_LATE_ARRIVAL`, `STALE_STREAM`, clock offset/drift |
| ORDERING | Did it arrive in order, once? | `OUT_OF_ORDER`, `DUPLICATE_PATTERN` |
| CONSISTENCY / CONTEXT | Does it match its own configured context? | `CONTEXT_INCONSISTENCY` |
| COMMUNICATION | Is the whole machine reachable? | `COMMUNICATION_LOSS` |
| SENSOR_HEALTH | Is the sensor itself behaving physically plausibly? | `SENSOR_DRIFT_SUSPECTED`, `STUCK_SENSOR_SUSPECTED`, `SPIKE_DETECTED` |
| CONFIGURATION | Did firmware/config change underneath us? | `CONFIG_CHANGE` |

Rule implementations live one module per dimension under `backend/app/data_quality/rules/`
(`completeness.py`, `validity.py`, `timeliness.py`, `ordering.py`, `consistency.py`,
`communication.py`, `sensor_health.py`, `configuration.py`). Every rule is a pure function —
`(event | points, context, policy) -> RuleIssue | None` — taking plain dataclasses
(`app.data_quality.domain.context.SensorContext/SensorInfo/TelemetryPoint`), never a live
ORM object, so every rule is unit-testable with zero database
(`backend/tests/data_quality/`, 54 tests).

Language stays calibrated per `docs/FAILURE_MODE_CATALOG.md`'s convention: sensor-health
issues say "SUSPECTED", never assert a fault outright, and never claim direct causality from
a simple correlation.

---

## 4. Severity, quality state, and eligibility

`IssueSeverity`: `INFO` < `WARNING` < `ERROR` < `CRITICAL`.

Two categorical, explainable output states are derived deterministically from the worst
severity among a sensor's current issues via one policy-configured mapping
(`demo_quality_policy.yaml`'s `eligibility_mapping`) — never two independent computations:

| Worst severity | `quality_state` | `eligibility` |
|---|---|---|
| NONE / INFO | `TRUSTED` | `ELIGIBLE` |
| WARNING | `USABLE_WITH_CAUTION` | `ELIGIBLE_WITH_CAUTION` |
| ERROR / CRITICAL | `UNUSABLE` | `INELIGIBLE` |

`quality_state` describes a sensor's overall current trustworthiness (what a person or a UI
badge should say); `eligibility` is the specific downstream-consumption decision Phase 8+
should check before trusting a reading. Both are kept as distinct fields (not collapsed into
one) per the brief's explicit request. **No numeric quality score** is computed for v1
(`quality_assessment.quality_score` stays a nullable column, always `NULL`) — the
categorical state plus the explicit issue list is the actual explainable output; a score
would imply false precision. Never `HEALTHY`/`FAILED` — those are condition-intelligence
words that don't exist yet.

---

## 5. Event-level vs. window-level assessment

- **Event-level** (`QualityEngine`, synchronous, per Kafka batch): needs only the current
  event plus small cached context on `sensor_quality_state` (previous value/sequence/
  timestamp). Covers missing/invalid/out-of-range/unit-mismatch/context-inconsistency,
  sequence gap, out-of-order, late arrival, duplicate-pattern, spike, config-change.
- **Window-level** (`WindowEvaluator`, a separate periodic asyncio task, default every 60s —
  `DATA_QUALITY_WINDOW_EVALUATION_INTERVAL_SECONDS`): needs a fresh time-range query against
  `telemetry` (via `TelemetryRepository`, reusing Phase 6's `ix_telemetry_tenant_sensor_time`
  index). Stateless and restart-safe — never trusts an in-memory rolling buffer. Covers
  staleness (sensor-type-aware expected cadence), sensor-drift-suspected, stuck-sensor-
  suspected, clock offset/drift, and machine-wide communication loss.

Event-scoped issues are immutable facts about one past event — created directly as
`RESOLVED` (nothing to "recover" from). Window-scoped issues represent an ongoing condition
and follow an `ACTIVE` → `RECOVERING` → `RESOLVED` lifecycle: a rule that stops firing
transitions `ACTIVE` → `RECOVERING` on the first clean evaluation cycle, then `RECOVERING` →
`RESOLVED` on the next — two consecutive clean cycles, avoiding flapping on one borderline
window.

---

## 6. Storage model

Deliberately **not** one row per event (that would 1:1-explode with telemetry volume):

- `sensor_quality_state` — one continuously-upserted row per `(tenant_id, sensor_id)`:
  current `quality_state`/`eligibility`, last-good/last-observed pointers, sequence/clock/
  staleness status, active issue count, firmware/config version markers. Cheap (bounded by
  sensor count, not event count), always current — the single place the frontend and API
  read a sensor's *current* state from.
- `quality_issue` — one row per *actually detected* issue, event- or window-scoped, only
  ever created when something is notable. Idempotency: event-scoped issues are
  `ON CONFLICT DO NOTHING` on `(tenant_id, sensor_id, rule_id, rule_version, event_id)`;
  window-scoped issues are `ON CONFLICT DO UPDATE` against a **partial unique index**
  covering only `status IN ('ACTIVE', 'RECOVERING')` — a plain constraint on the sliding
  `window_start`/`window_end` bounds would create a new row every single evaluation cycle
  instead of evolving one ongoing condition.
- `quality_assessment` — persisted for every window-level evaluation (low-frequency, one per
  sensor per policy interval regardless of outcome — a queryable trend/audit history at low
  cost) and for event-level evaluations that found at least one issue (linked 1:1 to that
  issue). A fully healthy single event never gets its own assessment row —
  `sensor_quality_state` is the always-current summary instead.

---

## 7. Policy configuration and versioning

`backend/app/data_quality/config/demo_quality_policy.yaml`, loaded by
`app.data_quality.config.policy.load_quality_policy()` (fail-fast pydantic validation,
`DATA_QUALITY_POLICY_PATH` env override). Carries the same disclaimer convention as every
other engineering-parameter file in this repository:

```
DEMO SYNTHETIC DATA QUALITY ASSUMPTIONS.
NOT VALIDATED PRODUCTION LIMITS.
```

`validity.value_ranges`/`expected_unit` are copied from (and must be kept in sync with)
`simulator/simulator/config/demo_engineering.yaml`'s `sensors:` block — deliberately not
imported at runtime, so this service works identically against a real, non-simulated
deployment with no simulator config at all. Every threshold (lateness, staleness cadence per
measurement type, clock drift tolerance, sensor-drift bias fractions, stuck-sensor window,
spike rate-of-change fractions, eligibility mapping) is configurable and carries a
`policy_version` recorded on every `quality_assessment`/`quality_issue` row, and every rule
carries its own independent `rule_version` — a policy or single rule can be revised and
reprocessed without touching the other.

---

## 8. Sensor-type and operating-state awareness

- Staleness expectation is per measurement type (`RPM`/`VIBRATION_*`/`PRESSURE` sampled
  every ~10s; `RESERVOIR_LEVEL`/`BEARING_TEMPERATURE` every ~30s) — never one global
  threshold.
- Stuck-sensor detection exempts measurement types where a constant value is legitimate on
  its own (`CYCLE_COMPLETION`, `PISTON_MOVEMENT`, `PUMP_RUNTIME`), and separately exempts an
  activity-correlated signal (`RPM`, `LOAD`, `VIBRATION_*`, ...) reading a constant value
  while every sample shares `operating_state == STOPPED` — RPM = 0 while stopped is not poor
  quality.
- Spike/rate-of-change detection only applies its limit when `operating_state` is unchanged
  since the previous reading — a real state transition (`STARTING` → `RUNNING`) is exactly
  when a large, legitimate jump happens, and is never flagged.

---

## 9. Firmware/configuration-change awareness

A firmware or controller version change is recorded as an INFO-severity `CONFIG_CHANGE`
marker, deliberately never itself treated as a fault — it matters because baseline behavior
may shift afterward (context Phase 8 will need), not because it is evidence of a problem
today.

---

## 10. Worker architecture and failure handling

`backend/app/data_quality/worker.py` runs two concurrent loops in one process
(`python -m app.data_quality.worker`, its own Kafka consumer group
`lubrisense-data-quality`, its own health/metrics port 8083):

- **Event-level loop**: consumes `lubrisense.telemetry.v1` in batches, exactly like Phase
  6's consumer. A **batch-level** transient failure (DB unreachable) retries with backoff
  and never commits offsets — identical to Phase 6, so quality processing never silently
  skips a batch. A **per-event** rule/persistence exception is isolated with a `SAVEPOINT`
  (`session.begin_nested()`), caught, logged, and counted
  (`quality_processing_errors` metric) — the batch still commits. This is a deliberate
  divergence from Phase 6's own precedent: Phase 6's consumer is the system of record and
  must never lose a telemetry row; the quality worker is secondary/advisory analysis that
  must never be allowed to stall real ingestion visibility over one bad rule evaluation on
  one event, and is fully recoverable via reprocessing.
- **Window-level loop**: every `DATA_QUALITY_WINDOW_EVALUATION_INTERVAL_SECONDS`, re-
  evaluates every currently-tracked sensor (queried from `sensor_quality_state`, not a
  per-tenant loop) and every machine those sensors belong to, with the same per-sensor/
  per-machine `SAVEPOINT` isolation.

`app/observability/metrics.py`/`worker_health.py` (relocated from `app/pipeline/` during
Phase 7, behavior-preserving — Phase 6's `verify_pipeline.sh` re-run clean after the move)
back `/health`, `/ready`, `/metrics` identically to Phase 6's workers.

---

## 11. Reprocessing

`python -m app.data_quality.reprocess --tenant-id ... --sensor-id ... --start ... --end ...`
re-runs event-level rules over a historical range under the **current** policy, reading
already-persisted `Telemetry` rows directly (everything `QualityEngine.process_event` needs
is already denormalized onto the telemetry row from the original enrichment — no Kafka
replay needed). Idempotent: unchanged `rule_version`s are a safe no-op
(`ON CONFLICT DO NOTHING`); a bumped `rule_version` writes new versioned rows without
touching or deleting the prior ones — provenance preserved, never overwritten.

**Known limitation**: context-dependent event-level rules (sequence gap, out-of-order,
spike) read the sensor's *current* live `SensorQualityState`, not its state as of the start
of the historical window being reprocessed. Acceptable for this reference implementation —
the primary reprocessing use case is re-scoring against an updated `rule_version`/policy,
not exact historical replay of context-dependent state.

---

## 12. API

Tenant-scoped via `get_current_tenant`, same convention as `app/api/v1/telemetry.py`
(`backend/app/api/v1/data_quality.py`):

- `GET /api/v1/data-quality/sensors/{sensor_id}` — current state + active issues (404 if the
  sensor doesn't exist for this tenant; `state: null` with a 200 is a valid "sensor exists,
  never observed yet" response).
- `GET /api/v1/data-quality/machines/{machine_id}` — every tracked sensor's state on that
  machine + active issues.
- `GET /api/v1/data-quality/issues` — filterable by `sensor_id`, `machine_id`, `severity`,
  `status`, time range.
- `GET /api/v1/data-quality/summary` — tenant-wide rollup: sensor counts by `quality_state`,
  active issue counts by `severity`.

---

## 13. Frontend

`frontend/src/app/data-quality/page.tsx` — summary cards (sensors tracked, TRUSTED/USABLE
WITH CAUTION/UNUSABLE counts) plus a filterable (status, severity) issues table. Badges show
`TRUSTED`/`USABLE_WITH_CAUTION`/`UNUSABLE` — never `HEALTHY`/`FAILED`. No health score, no
diagnosis, no recommendation — this is a data-quality signal only, matching LOOP.md's
"never generate production-like health values inside React" and CLAUDE.md's product-story
boundary (Phase 7 is DATA → DATA QUALITY, not yet DETECTION/DIAGNOSIS/DECISION).

---

## 14. Known limitations

- **Window-scoped mean-shift dilution**: `check_sensor_drift` splits the whole configured
  lookback window (`sensor_drift.window_minutes`, 180 min default) in half by sample count
  and compares means. On a sensor with a lot of *older, non-drifted* telemetry already
  sitting inside that window (e.g. a demo/reference sensor re-used across many manual test
  sessions), a genuinely fresh drift trend can be diluted if it's a small fraction of an
  otherwise-long, stable history. A freshly onboarded sensor in a real deployment does not
  have this problem. Verified correct in isolation
  (`backend/tests/data_quality/test_sensor_health.py::test_sensor_drift_detected`) and
  against a live, undiluted narrow time range — the rule logic itself is correct; a future
  revision could instead compare a short recent window against a longer stable baseline.
- **Reprocessing context**: see §11 above.
- **No numeric quality score**: see §4 above — an intentional v1 scope decision, not a gap.
- **Communication-loss attribution**: `QualityIssue.sensor_id` is `NOT NULL`, so a machine-
  wide `COMMUNICATION_LOSS` issue is recorded against one deterministically chosen
  representative sensor on the machine (lowest sensor UUID) rather than against the machine
  alone — `machine_id` is a proper column and the intended way to query/filter this issue,
  not `sensor_id`.
- **False-positive rate on healthy data**: measured live on a clean 1,571-event healthy edge
  session with zero scenarios injected — zero `WARNING`/`ERROR`/`CRITICAL` issues, only
  `OUT_OF_ORDER` at `INFO` severity (~23% of events), attributable to genuine wire-level
  reordering under a fast synthetic burst (20ms/tick, background async sender thread), not a
  rule flaw — `INFO` never degrades `quality_state`/`eligibility`. See the Phase 7 final
  report for the full measurement.

---

## 15. Phase boundary

Not implemented in Phase 7 (explicitly out of scope — see `IMPLEMENTATION_STATUS.md`):
baselines, a rules engine, feature engineering, ML inference, Kalman/state estimation,
condition intelligence, decision intelligence, incidents, RAG, GenAI agents, CMMS
integration, the final product UI. `sensor_quality_state.eligibility` is the contract Phase
8+ must read before trusting a reading — nothing in Phase 7 acts on that judgment itself.
