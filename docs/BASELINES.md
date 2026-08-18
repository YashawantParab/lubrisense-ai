# Baselines — Phase 8 Design & Implementation

Status: COMPLETE (Phase 8). See `IMPLEMENTATION_STATUS.md` for the verification record and
`TECHNICAL_DECISIONS.md` (ADR-071–ADR-076) for the architectural decisions.

## 1. Purpose

The baseline engine answers one question, for every sensor, continuously:

> **"What is normal for this sensor on this asset, under this operating condition?"**

It is Machine & Sensor Intelligence infrastructure (`CLAUDE.md`'s three-layer model) — it
does not diagnose faults, does not classify anomalies, and does not produce maintenance
recommendations. It produces a durable, versioned, queryable answer to "what is normal"
that later phases (Phase 9 rules, Phase 10 feature engineering, Phase 11 ML, Phase 12
Kalman/state estimation, Phase 13 condition intelligence) consume as an input, not as a
verdict.

A baseline is **not** a universal threshold. `bearing temperature at 20% load` is not
comparable to `bearing temperature at 90% load` — see §5 "Context dimensions".

## 2. Architecture

```
backend/app/baselines/
  domain/        pure, DB-free data + math: context, statistics, deviation,
                  reservoir_trend, cycle_metrics, anchor (MAD distance)
  config/        BaselinePolicy (pydantic) + demo_baseline_policy.yaml
  strategies/    thin adapters wiring quality-gated telemetry into domain/ math:
                  static_reference, rolling, contextual, reservoir, cycle
  services/      orchestration: BaselineEngine, promotion (contamination-control
                  state machine), fallback, deviation_service, summary_service,
                  query_service
  repositories/  BaselineProfileRepository — the only writer of `baseline_profile`
  workers/       worker.py (periodic live refresh), backfill.py (historical CLI)
```

This mirrors the Phase 7 data-quality module's shape (`domain/services/repositories/
rules-or-strategies/workers` + a versioned YAML policy) deliberately — same architectural
family, same review muscle-memory.

`BaselineEngine` (`services/baseline_engine.py`) is the single orchestrator. Both the live
worker (`workers/worker.py`, recent-window refresh) and the historical backfill CLI
(`workers/backfill.py`, an explicit `--start`/`--end` range) call the exact same
`refresh_sensor`/`refresh_machine_cycle` methods — `window_override` is the only difference
between "live" and "historical" operation (brief §28's "simple architecture that supports
both").

The baseline engine consumes only persisted Phase 6 `telemetry` rows plus Phase 7
`sensor_quality_state` — it never re-runs the simulator and never imports
`app.data_quality`'s rule modules directly (only its `SensorQualityStateRepository`, the
same read-only dependency `app.pipeline`/`app.data_quality` already established as the
correct layering).

## 3. Engineering limits vs. learned baselines

These are two structurally distinct things, kept in two distinct `BaselineStrategyType`
lineages that never overwrite each other:

| | Engineering limit | Learned baseline |
|---|---|---|
| Strategy | `STATIC_ENGINEERING_REFERENCE` | `ROLLING_ASSET_BASELINE` / `CONTEXTUAL_ASSET_BASELINE` |
| Source | `demo_baseline_policy.yaml`'s `engineering_reference.value_ranges` (a physically-possible range per sensor type, kept in sync with the simulator's own `demo_engineering.yaml` and the data-quality engine's `validity` ranges) | Actual eligible telemetry for this specific sensor |
| Says | "this value should never exceed X" | "this asset normally operates around Y under context Z" |
| Learns/adapts | Never — created once, `ACTIVE` forever (`refresh_interval_seconds`/`stale_after_seconds` set to a ~317-year sentinel) | Continuously, subject to the contamination-control gate (§7) |
| Sample count | Always `0` — it is config-derived, not observed | Real, tracked, gates every state transition |

`STATIC_ENGINEERING_REFERENCE` is created once per sensor the first time
`BaselineEngine.refresh_sensor` runs for it, and is never mutated afterward. It exists so
the fallback chain (§6) always has *something* to return, even for a sensor with zero
telemetry history, and so a learned baseline is never silently trusted as a hard safety
limit — a distinction later phases (rules, condition intelligence) must preserve, not
collapse into one number. See ADR-071.

## 4. Baseline strategies

| Strategy | What it is | Built for |
|---|---|---|
| `STATIC_ENGINEERING_REFERENCE` | Config-derived reference band, never learned | Every sensor, always, as the fallback of last resort |
| `ROLLING_ASSET_BASELINE` | Robust statistics over a rolling window of this sensor's own eligible telemetry, unsegmented | Every sensor, always |
| `CONTEXTUAL_ASSET_BASELINE` | `ROLLING_ASSET_BASELINE`, segmented by operating-state/cycle-phase context | Sensor types in `contextual_measurement_types` (§5) |

`RESERVOIR_LEVEL` additionally gets a `metric_kind=RESERVOIR_TREND` variant (§8) and
`PRESSURE` a machine-scoped `metric_kind=CYCLE_METRIC` variant (§9), both still persisted as
`BaselineProfile` rows (own `context_key`), not a separate table — `metric_kind`
distinguishes "how to interpret `statistics`", not a different lineage mechanism.

No ML model is used anywhere in this phase (brief §3/§51) — every strategy is a
deterministic statistical computation over a sample set.

## 5. Context dimensions

`BaselineContext` (`domain/context.py`) carries exactly two fields:

- `operating_state` — `STOPPED` / `RUNNING_LOW_LOAD` / `RUNNING_NORMAL_LOAD` /
  `RUNNING_HIGH_LOAD` (the real Phase 3 `OperatingProfile` states;
  `STARTING`/`SHUTTING_DOWN` are transitional and excluded from contextual segmentation,
  still included in the unsegmented rolling baseline)
- `cycle_phase` — `ACTIVE` / `IDLE`, derived per-reading from whether the *same-timestamp*
  value exceeds a sensor-type-specific `cycle_phase_idle_threshold` (not the simulator's
  internal 5-state cycle machine, which is hidden state — see ADR-072)

Load and RPM are **not** separate dimensions. This reference implementation's Phase 3
operating-state machine already derives `RUNNING_{LOW,NORMAL,HIGH}_LOAD` from configured
load bands, so `operating_state` already carries the load/RPM signal a real deployment would
otherwise reconstruct via a separate LOAD/RPM sensor correlation join. See ADR-072 for the
full rationale, including why this is documented as a reference-implementation
simplification, not a claim that load/RPM conditioning is unnecessary in general.

Ambient/lubricant temperature is **not** used as a conditioning dimension for other sensor
types — no distinct ambient-temperature measurement type exists in this system.
`LUBRICANT_TEMPERATURE` gets its own baseline (as any other sensor type does); it is not
used to condition e.g. `BEARING_TEMPERATURE`.

`context_dimensions_for(measurement_type)` (config-driven) says which of the two dimensions
apply per sensor type:

| Sensor type | Dimensions | Why |
|---|---|---|
| `PRESSURE`, `FLOW`, `PUMP_CURRENT` | `operating_state`, `cycle_phase` | Cycle-coupled signals — flat-to-zero outside an active delivery cycle |
| `VIBRATION_RMS`, `VIBRATION_PEAK`, `BEARING_TEMPERATURE`, `RPM`, `LOAD` | `operating_state` only | Load/RPM-dependent, not cycle-coupled |
| `RESERVOIR_LEVEL` | none (trend-based, §8) | Directional, not a bucketed distribution |
| `PUMP_RUNTIME`, `CYCLE_COMPLETION`, `PISTON_MOVEMENT`, `LUBRICANT_TEMPERATURE` | none | Rolling-only; no strong context dependence modeled in this reference implementation |

Contextual profiles are only built for the four "stable" operating states — a transitional
state (`STARTING`/`SHUTTING_DOWN`) never gets its own bucket (too few, too heterogeneous
samples), but its readings still count toward the unsegmented `ROLLING_ASSET_BASELINE`.

## 6. Fallback hierarchy

`services/fallback.py::resolve_baseline` — never silently returns an unrelated context; each
rung is an explicit lookup, and the caller always learns which rung actually answered via
`BaselineSourceKind`:

```
EXACT_CONTEXT           (operating_state + cycle_phase, if the sensor type uses both)
  -> OPERATING_STATE     (operating_state only, if the sensor type uses cycle_phase too)
  -> SENSOR_LEVEL         (ROLLING_ASSET_BASELINE, unsegmented)
  -> ENGINEERING_REFERENCE (STATIC_ENGINEERING_REFERENCE)
  -> NONE                 (nothing exists yet for this sensor at all)
```

Only rungs that ever get an `ACTIVE` row for the resolved context are actually tried — a
sensor type with no `cycle_phase` dimension skips straight from `EXACT_CONTEXT` (which, for
it, means "operating_state only") to `SENSOR_LEVEL`. See ADR-074.

## 7. Quality gating

Only telemetry Phase 7 marked `ELIGIBLE` or `ELIGIBLE_WITH_CAUTION` (`SensorQualityState.
eligibility`) may ever reach a strategy's statistics computation, and within that, only rows
whose own `Telemetry.quality == GOOD` (a sensor can be individually `ELIGIBLE` at the
window level while a specific reading is itself flagged bad). `INELIGIBLE` sensors
contribute **zero** samples — never a fabricated statistic, never a partial one — see
`test_ineligible_sensor_never_updates_learned_baseline`.

`ELIGIBLE_WITH_CAUTION` samples are included in every statistic (not excluded, not
down-weighted numerically) but tracked separately via `RobustStatistics.caution_count`, so a
caller can see how much of a baseline's evidence came from caution-flagged data without the
engine silently discarding real evidence (brief §5's "explicit weighting or exclusion
rules" — the explicit rule chosen here is "include and count separately", not "exclude" or
"numerically down-weight").

## 8. Reservoir trend baseline

`RESERVOIR_LEVEL` is directional, not a symmetric distribution — a "normal reservoir level"
band around a fixed mean is meaningless for a signal that monotonically depletes between
refills (Phase 3/4's own reservoir model). `domain/reservoir_trend.py` instead computes:

- `depletion_rate_per_hour` — robust (median-of-slopes) rate between consecutive readings
- `refill_count` — number of upward jumps detected in the window
- `time_since_last_refill_hours`
- the underlying `RobustStatistics` of the raw level values themselves (kept as
  supplementary context, not the primary signal)

Stored as its own `context_key="trend"` / `metric_kind=RESERVOIR_TREND` row, alongside (not
instead of) the plain unsegmented `ROLLING_ASSET_BASELINE` row for `RESERVOIR_LEVEL` — brief
§24 says "do not use ONLY symmetric bands", not "never compute one at all".

## 9. Cycle-level baseline

Machine-scoped (not sensor-scoped — a lubrication cycle is a property of the pump/circuit as
a whole), computed from a machine's `PRESSURE` and `CYCLE_COMPLETION` telemetry together
(`domain/cycle_metrics.py`): pressure rise time, peak pressure, cycle duration, and
completion success rate, segmented into cycles via the same active/idle threshold used for
`cycle_phase` context (§5). Recorded against one deterministically chosen representative
`PRESSURE` sensor on the machine (lowest `sensor_id`) — `BaselineProfile.sensor_id` is
`NOT NULL`, and `machine_id` is the real column to query this profile by, mirroring Phase
7's `COMMUNICATION_LOSS`-attributed-to-one-sensor precedent
(`app.data_quality.services.window_evaluator`) for the identical structural reason.

## 10. Contamination control (mandatory — brief §41)

This is the most safety-critical piece of Phase 8: **a developing fault must never
gradually redefine "normal."**

`services/promotion.py::decide` is a pure, fully unit-tested state machine (no database) —
`BaselineEngine` only translates its `PromotionDecision` into repository calls. Core idea:

> A candidate must diverge from, then **remain stably diverged** from, the currently
> `ACTIVE` anchor for `required_stable_cycles` consecutive worker cycles before it replaces
> the anchor. "Stability" for a diverged candidate is measured cycle-over-cycle against the
> *previous candidate snapshot*, not against the fixed anchor — but the very first
> divergence check (whether to start candidate-tracking at all) **is** against the fixed
> anchor.

This combination is what prevents both failure modes:

1. **A single-cycle blip never promotes** — needs `required_stable_cycles` (default `2`)
   consecutive confirmations, each measured as a fresh robust (median/MAD) distance
   (`domain/anchor.py::mad_distance`) below `candidate_divergence_mad_multiplier` (default
   `3.0`) from the prior candidate snapshot.
2. **A slow, continuous drift never "boils the frog"** — `REFINE_ACTIVE` (the action that
   updates the `ACTIVE` row's own `statistics` in place, without a version bump) only fires
   when a cycle's fresh stats are still close to the **anchor itself**. Once a cycle drifts
   past that threshold, the anchor stops moving entirely and a separate candidate begins
   tracking; the candidate only ever replaces the anchor via an explicit `PROMOTE`
   (version bump, `SUPERSEDED` recorded on the old row), and `PROMOTE` only fires once the
   candidate has genuinely settled — stayed within tolerance of *itself* across multiple
   cycles — not merely "far from the anchor once." During the entire onset window before
   that happens, every live comparison (`deviation_service`, the `/current` API) keeps using
   the pre-drift anchor.

Verified directly against live Postgres:

- `test_gradual_drift_leaves_active_baseline_anchored` — a Phase 4-style gradual-restriction
  pressure rise (9.0 -> 18.0 bar) leaves the `ACTIVE` row's `id` and `statistics.median`
  completely unchanged after one drifted refresh cycle — no quality flag involved at all
  (eligibility stays `ELIGIBLE` throughout); this is the contamination-control state machine
  alone protecting against a genuine physical fault, independent of Phase 7.
- `test_ineligible_sensor_never_updates_learned_baseline` — the Phase 7 quality-gating layer
  (§7 above) independently protects against a sensor whose *quality* has degraded
  (drift/dropout/communication loss flagged `INELIGIBLE`) ever contributing samples at all.

Both protections are real and independent: quality gating stops a sensor Phase 7 has already
flagged as untrustworthy; the stability gate stops a sensor that is still reporting
`GOOD`-quality, `ELIGIBLE` readings but whose *physical value* is genuinely changing (a
developing fault, not a sensor fault) from creeping the anchor. See ADR-073.

## 11. Firmware / config-change awareness

`BaselineEngine._apply_config_change_check` (brief §17/§18): if a sensor's
`firmware_version` or `controller_version` (carried on every `Telemetry` row since Phase 6)
materially changes since the current lineage's row was last stamped, that row is invalidated
(`BaselineState.INVALIDATED`, `invalidation_reason` recorded — only if it had reached
`ACTIVE`/`STALE`; nothing to invalidate for a still-`BUILDING` row) and a fresh generation
begins at the next version number for that `(sensor, strategy, context_key)` lineage.
Pre-/post-change behavior is never blended into one baseline. Verified:
`test_firmware_change_invalidates_and_starts_new_generation`.

## 12. Robust statistics

`domain/statistics.py::compute_robust_statistics` computes `count`, `caution_count`, `mean`,
`stddev`, `median`, `mad` (median absolute deviation, scaled by `1.4826` to be a consistent
estimator of stddev under normality), `p05`/`p25`/`p75`/`p95` (linear-interpolation
quantiles), `min`, `max` — never only mean/stddev, so a handful of transient spikes or a
brief sensor hiccup does not dominate the summary the way it would a plain mean (brief §13).
Mean/stddev are still computed and stored (useful for roughly-symmetric signals like
`LOAD`/`RPM`, and as `deviation.py`'s fallback path for a degenerate zero-MAD distribution),
just never relied on alone. See ADR-076.

## 13. Minimum evidence / readiness model

Every `(sensor, strategy, context_key)` lineage has a `min_sample_required` (config-driven,
sensor-type-aware — e.g. `30` default, `10` for `CYCLE_COMPLETION`/`PUMP_RUNTIME`, `20` for
`RESERVOIR_LEVEL`). Below that count, the profile is `INSUFFICIENT_DATA` with
`statistics=null` — never a fabricated statistic from too few points.

`services/summary_service.py::BaselineSummaryService` computes **readiness** (`READY` /
`PARTIAL` / `NOT_READY`), an aggregate over a sensor's or machine's current
`ROLLING_ASSET_BASELINE`/`CONTEXTUAL_ASSET_BASELINE` rows only (the always-`ACTIVE` static
reference is deliberately excluded from this rollup — it would make every sensor trivially
"ready"). This is explicitly **baseline readiness**, not asset/machine health (brief §26/§43
— condition intelligence, a later phase, owns health).

## 14. Baseline states

`BaselineState`: `INSUFFICIENT_DATA -> BUILDING -> ACTIVE -> [STALE] -> [INVALIDATED |
SUPERSEDED]`.

- `INSUFFICIENT_DATA` — not enough eligible samples yet; no row existed, or the row exists
  but never accumulated enough evidence.
- `BUILDING` — enough samples exist and a candidate is accumulating stability-gate
  confirmations, but has not yet been confirmed `required_stable_cycles` times.
- `ACTIVE` — the current anchor; live comparisons use this row's `statistics`.
- `STALE` — was `ACTIVE`, but no refresh has landed within `stale_after_seconds` (§15); still
  the best available anchor (still returned by the fallback chain), just flagged as aging.
- `INVALIDATED` — explicitly ended (firmware/config change, §11); never deleted, kept for
  provenance; excluded from "current" lookups.
- `SUPERSEDED` — replaced by a `PROMOTE`d successor version; never deleted; excluded from
  "current" lookups.

`INVALIDATED`/`SUPERSEDED` are the two terminal states — a `(sensor, strategy, context_key)`
lineage has at most one non-terminal ("current") row at any time
(`BaselineProfileRepository.get_current`), enforced by application discipline (every write
path goes through the repository's `create_initial`/`update_in_place`/`promote`/`invalidate`
methods, never a raw insert after the first version).

## 15. Versioning

Every `BaselineProfile` row carries `version` (integer, starting at `1` per lineage,
incrementing on every `PROMOTE` and on every fresh generation after an invalidation — never
reused, even across an invalidation gap), plus `config_version` (the policy YAML's own
`policy_version`) and `quality_policy_version` (Phase 7's policy version, snapshotted at
write time). Nothing is ever mutated in a way that loses history: `update_in_place` only
touches candidate-tracking/statistics fields on the *current* row (never bumps version,
matching idempotency, §17), and `promote` always inserts a new row rather than overwriting.
`list_versions_for_sensor` returns full lineage history, including superseded/invalidated
rows.

## 16. Rolling windows

Sensor-type-aware, not one global window (`rolling_window_seconds_for`): `24h` default,
`7d` for `RESERVOIR_LEVEL`/`PUMP_RUNTIME` (a trend needs multiple refill cycles to be
meaningful). Refresh cadence is likewise sensor-type-aware (`refresh_interval_seconds_for`):
`15min` default, `1h` for `RESERVOIR_LEVEL`/`PUMP_RUNTIME`. Staleness threshold
(`stale_after_seconds_for`): `1h` default, `6h` for `RESERVOIR_LEVEL`.

## 17. Idempotency

Reprocessing the same telemetry/window/config never creates a duplicate `ACTIVE` version.
Two consecutive refresh cycles over an unchanged sample set both resolve to `REFINE_ACTIVE`
(update in place) or `FREEZE` (no new evidence), never `PROMOTE` — `promote` is only reached
through the stability-gate's `on_confirmed` branch, which requires a *new*, sustained
divergence from the current anchor. Verified live:
`test_idempotent_refresh_does_not_duplicate_active_version` (unit) and
`scripts/verify_baselines.sh` step 6 (a third identical `backfill` run against live Postgres
still leaves exactly one `ROLLING_ASSET_BASELINE` row).

## 18. Deviation helper (not fault diagnosis)

`domain/deviation.py::compute_deviation` — a robust standardized distance
(`|value - median| / mad`, falling back to a stddev-based distance if `mad == 0`, and to a
degenerate constant-check if both are zero, e.g. `CYCLE_COMPLETION`), classified into
`WITHIN_EXPECTED_RANGE` / `MILD_DEVIATION` / `STRONG_DEVIATION` against configurable
`mild_multiplier`/`strong_multiplier` (default `2.0`/`4.0`), plus a quantile-position view
relative to `[p05, p95]`. This is explicitly **not** anomaly/fault classification — no
severity, no "faulty" label, no recommendation. It exists so a later rules/ML/
condition-intelligence phase has an explainable distance to build on, not a verdict.

## 19. Machine-level baseline summary / tenant summary

`GET /api/v1/baselines/machines/{machine_id}` returns per-sensor profiles plus a
machine-level `Readiness` rollup; `GET /api/v1/baselines/summary` returns a tenant-wide
count-by-state. Both answer "how ready is the baseline layer", explicitly not
"how healthy is this machine" (brief §26/§43 — see §13 above).

## 20. Persistence

One table, `baseline_profile` (migration `3366bbb38e2a`, chained off Phase 7's
`5257a5e8e595`) — a deliberately denormalized schema rather than the brief's illustrative
three-table split (`baseline_profiles`/`baseline_statistics`/`baseline_contexts`):
`statistics`/`candidate_statistics`/`context` are `JSONB` columns on the same row as the
version/state/window metadata, because a `BaselineProfile` row *is* one immutable(-once-
`ACTIVE`) snapshot — splitting statistics into a child table would only add a join for data
that is always read and written together, never independently. See ADR-071 for the full
comparison against the alternative schema. Composite tenant FKs (`ADR-022`'s pattern) to
`tenant`/`sensor`/`machine`; unique partial index `uq_baseline_profile_active` enforces at
most one `ACTIVE` row per `(tenant_id, sensor_id, strategy, context_key)`; `uq_
baseline_profile_version` enforces version uniqueness per lineage.

## 21. Worker

`python -m app.baselines.workers.worker` — **not** a Kafka consumer, unlike the Phase 6
telemetry consumer or the Phase 7 data-quality worker. The baseline engine reads
already-persisted `telemetry` directly rather than reacting to individual events (brief
§6's "do not re-run the simulator", and there is no single-event baseline decision to make —
a baseline is a statistic over a window). A periodic asyncio loop is the right shape instead
(default cycle interval configurable, `BASELINE_WORKER_CYCLE_SECONDS`). See ADR-075.

Each cycle: discover every currently-tracked sensor from `sensor_quality_state`
(cross-tenant, mirroring `app.data_quality.worker`'s own discovery pattern), skip any sensor
whose measurement-type-specific `refresh_interval_seconds` hasn't elapsed since its
`last_evaluated_at` (brief §29 — not every profile refreshes on an identical cadence), refresh
it, refresh cycle-level baselines once per distinct machine seen, then sweep for staleness
(`stale_after_seconds` exceeded since `last_evaluated_at` -> `mark_stale`). Per-sensor/
per-machine failures are isolated with a `SAVEPOINT`, matching Phase 7's worker precedent —
one bad sensor never blocks the cycle. Own health/metrics server
(`app.observability.worker_health.WorkerHealthServer`, the same shared component Phase 7
relocated for exactly this kind of reuse) on a dedicated port
(`BASELINE_WORKER_HEALTH_PORT`).

## 22. Historical backfill

```
python -m app.baselines.workers.backfill \
  --tenant-id <uuid> [--sensor-id <uuid>] --start <iso8601> --end <iso8601>
```

Calls the exact same `BaselineEngine.refresh_sensor`/`refresh_machine_cycle` methods as the
live worker, with `window_override=(start, end)` instead of "now minus the configured
rolling window" — never deletes prior versions (a backfill run participates in the normal
promotion/stability-gate machinery, so it can only ever produce a new version through the
normal contamination-control path). Without `--sensor-id`, backfills every sensor currently
tracked in `sensor_quality_state` for the tenant.

## 23. Observability

`baseline_events_processed`, `baseline_profiles_created`, `baseline_profiles_updated`,
`baseline_profiles_invalidated`, `baseline_build_failures`, `baseline_build_duration_seconds`,
`baseline_insufficient_data`, `baseline_stale_profiles` — exposed via the shared
`WorkerMetrics`/Prometheus-text `/metrics` endpoint (`app.observability.metrics`, `app.
observability.worker_health`), same convention as the Phase 6/7 workers.

## 24. API

All tenant-scoped via `get_current_tenant` (the same `X-Tenant-ID` header convention as
every other Phase 2+ endpoint):

- `GET /api/v1/baselines/sensors/{sensor_id}` — every current (non-terminal) profile for a
  sensor, plus sensor-level readiness.
- `GET /api/v1/baselines/sensors/{sensor_id}/current?operating_state=&cycle_phase=&value=` —
  resolves through the fallback hierarchy (§6) for the given (optional) context, and if
  `value` is supplied, also returns the deviation (§18) of that value against the resolved
  baseline.
- `GET /api/v1/baselines/machines/{machine_id}` — every current profile across all sensors
  on a machine, plus machine-level readiness.
- `GET /api/v1/baselines/summary` — tenant-wide profile count by state.

## 25. Frontend validation view

`/baselines` — a plain validation table (sensor, machine, strategy, context, state, sample
count, last evaluated), sourced entirely from the API above via a `useBaselines`
TanStack Query hook (`frontend/src/hooks/use-baselines.ts`,
`frontend/src/lib/api/baselines.ts`) — no hardcoded values, no AI diagnosis, matching
ADR-008. A sensor detail view additionally renders the resolved baseline's robust-statistics
band (median/MAD, p05–p95) against recent telemetry for visual sanity-checking, not as a
finished analytics product.

## 26. Contamination-control summary (brief §41's explicit ask)

> "Define how the system avoids learning faulted/degraded behavior as normal."

Two independent, layered protections:

1. **Quality gating (§7)** — a sensor Phase 7 has already flagged `INELIGIBLE` (severe
   drift, dropout, communication loss, invalid/missing readings) contributes zero samples.
   This alone stops most of Phase 4's synthetic sensor-fault catalog from ever reaching the
   baseline engine.
2. **Candidate/stability-gate promotion (§10)** — independent of quality flags, a sensor
   still reporting `GOOD`-quality, `ELIGIBLE` readings but whose underlying *physical*
   behavior is genuinely changing (a developing fault — gradual restriction, pump
   degradation) cannot move the `ACTIVE` anchor except through a candidate that has
   proven itself stable across multiple consecutive refresh cycles, and even then only
   via an explicit, auditable `PROMOTE` (new version, old version `SUPERSEDED`, both kept).

Neither mechanism alone is "the baseline decides what is normal" circular logic — quality
gating is decided entirely outside the baseline engine (by Phase 7's independent rule
evaluation), and the stability gate is a fixed, symmetric statistical test that has no
concept of "good"/"bad" direction (it would equally resist a sudden *improvement*
settling in prematurely).

## 27. Known limitations / synthetic-demo assumptions

- `engineering_reference.value_ranges` in `demo_baseline_policy.yaml` are explicit demo
  synthetic assumptions (file header disclaimer), not validated industrial specifications —
  same posture as `simulator/simulator/config/demo_engineering.yaml` and `backend/app/
  data_quality/config/demo_quality_policy.yaml`, and kept numerically in sync with both.
- Load/RPM conditioning is folded into `operating_state` rather than modeled as independent
  continuous buckets (§5) — a reasonable simplification given this reference
  implementation's discrete Phase 3 operating-state machine, but a real deployment with
  continuously-varying load (not discrete shift-driven bands) would likely want genuine
  load/RPM buckets as the brief's illustrative §9 describes.
- No ambient-temperature conditioning dimension exists for any sensor type other than
  `LUBRICANT_TEMPERATURE` having its own baseline — no distinct ambient-temperature
  measurement type exists in this system to condition on.
- `CLASS_REFERENCE` (fleet-wide secondary fallback, brief §42) is **not implemented** —
  `STATIC_ENGINEERING_REFERENCE` already serves as the non-asset-specific fallback of last
  resort, and this reference implementation's fleet (one flagship conveyor plus a handful of
  other seeded machines) does not yet warrant a second, class-level statistical layer. Every
  learned baseline (`ROLLING_ASSET_BASELINE`/`CONTEXTUAL_ASSET_BASELINE`) is asset-specific
  by construction (`sensor_id`-scoped), so the brief's core requirement — "no machine
  redefines another machine's normal" — holds regardless.
- The backfill CLI and live worker read the sensor's *current* `sensor_quality_state.
  eligibility`/`policy_version`, not a historical point-in-time eligibility — the same
  known limitation Phase 7's own reprocessing CLI documents (`docs/DATA_QUALITY.md` §14,
  ADR-070), inherited here rather than re-solved.
- Cycle-phase segmentation uses a simple value-vs-threshold check per reading, not the
  simulator's own 5-state hidden cycle machine (`IDLE -> PUMP_START -> PRESSURE_BUILD ->
  FLOW_DELIVERY -> COMPLETING`) — deliberately, since that hidden state is exactly what
  Phase 3's ground-truth separation (ADR-032) forbids the baseline engine (a
  telemetry-only consumer) from seeing. The threshold-based proxy is coarser but derived
  entirely from observable telemetry, matching every other Phase 6+ pipeline consumer's
  boundary.
