# State Estimation — Phase 12

**This is a demo synthetic state-estimation implementation and is not validated for
production machinery.** Every numeric assumption below (thresholds, noise intensities,
time constants) is a labeled reference default — see
`backend/app/state_estimation/config/state_estimation_v1.yaml`'s own disclaimer.

## Purpose

Machine & Sensor Intelligence (CLAUDE.md's three-layer architecture) needs more than rules
and ML classification: a continuous, explainable estimate of an asset's underlying
condition, filtered from noisy point-in-time observations, that answers:

- "What underlying lubrication-delivery/bearing condition best explains the noisy sensor
  evidence over time?"
- "Is the estimated condition stable, improving, or deteriorating?"

State estimation produces **evidence**, not a diagnosis or maintenance decision — Phase 13
Condition Intelligence is what will later combine this with Phase 9 rule findings and
Phase 11 ML output as three distinct evidence sources (Phase 12 brief §31; see "ML
independence" below).

## State definitions

Two independent Kalman filters, each tracking its own 2-element state
`[level, rate]`:

| State type | `level` meaning | Disjoint from |
|---|---|---|
| `LUBRICATION_DELIVERY_STATE` | 0.0 = nominal delivery, 1.0 = severely degraded delivery | `BEARING_CONDITION_STATE` |
| `BEARING_CONDITION_STATE` | 0.0 = nominal bearing condition, 1.0 = severely degraded | `LUBRICATION_DELIVERY_STATE` |

`level` is a **normalized condition state, not a failure probability** — the two are
different things (a 0.8 level does not mean "80% chance of failure"). `rate` is `level`'s
instantaneous rate of change, in state-units per second; it is what `trend`
(`IMPROVING`/`STABLE`/`DETERIORATING`/`UNKNOWN`) is derived from — never a separate
heuristic.

The two states are estimated by **separate `StateEstimator` instances with disjoint
observation channels** (see below) — this is what makes it possible for bearing condition
to deteriorate while delivery evidence stays nominal, and vice versa (Phase 12 brief §26,
verified live — see "Independent bearing result" in the final report).

## Observation model

Both filters consume the same Phase 10 `STATE_ESTIMATION_V1` feature set (already defined
in Phase 10, version `1.0.1` — Phase 10 itself performs no state estimation, it only
anticipated this consumer). Each state type is configured with a small list of observation
channels, each reading one already-baselined Phase 10 feature:

| State type | Channels |
|---|---|
| `LUBRICATION_DELIVERY_STATE` | `pressure.robust_deviation`, `flow.robust_deviation`, `pump_current.robust_deviation`, `reservoir_level.robust_deviation` |
| `BEARING_CONDITION_STATE` | `bearing_temp.robust_deviation`, `vibration_rms.robust_deviation` |

`{stem}.robust_deviation` (Phase 10) is `|delta_from_baseline| / MAD` against an ACTIVE
Phase 8 baseline — already non-negative, already contextualized against the
operating-state-segmented baseline profile (`context_requirements: operating_state,
cycle_phase`), so this estimator does not re-derive operating-context normalization
itself (matching ADR-080's precedent: reuse Phase 7/8 output directly, no parallel policy
layer).

**Why `robust_deviation`, not raw cycle-timing features** (`cycle.pressure_rise_time`,
`cycle.duration`, ...), even though the Phase 12 brief lists them as usable: those features
have no existing Phase 8 baseline to normalize against. Adding one here would mean
re-implementing Phase 8's own baselining logic for this estimator alone. A natural v2
extension, not an oversight — see "Limitations" below.

### Calibration transform: feature → Kalman observation `z`

`robust_deviation` is unbounded ("how many MADs away from the baseline"), but the Kalman
filter's state lives in `[0, 1]`. Each channel applies a fixed, non-state-dependent
transform before the value ever reaches the filter:

```
normalized_evidence = min(|robust_deviation| / mad_scale, 1.0)
```

`mad_scale` (config, per channel) is the number of MADs treated as "fully saturated
evidence of degradation" (default 6.0 for hydraulic/bearing channels, 8.0 for the weaker
reservoir-level proxy). This transform is deliberately **magnitude-based, not
signed** — a large deviation in *either* direction from baseline is evidence of an
abnormal delivery condition; the estimator does not assume a fixed sign per fault type
(restriction/leakage/blockage can push pressure in different directions depending on
sensor placement). This matches the Phase 12 brief's own boundary: "state estimator
estimates condition, not fault type" (§24) — magnitude-based evidence keeps it
fault-agnostic, unlike Phase 11's classifier, which is explicitly allowed to be
fault-specific.

## Kalman model: x_k, F, H, Q, R, P

- **`x_k`** — `[level, rate]`, the 2x1 state vector.
- **`F(dt, g)`** — state-transition matrix for a *mean-reverting-velocity* model:
  `level_next = level + rate*dt`, `rate_next = rate * g`, where
  `g = exp(-dt / rate_decay_tau_seconds)`.
- **`H`** — `[1, 0]` for every channel: each observation reads `level` directly; `rate` is
  never observed directly, only inferred from how `level` moves across ticks.
- **`Q(dt)`** — `diag(q_level * dt, q_rate * dt)`, an independent per-second diffusion
  model.
- **`R`** — one channel's measurement-noise variance for this tick (`base_variance`,
  quality-inflated — see below).
- **`P`** — the 2x2 state-covariance matrix.

### Why `g` (mean-reverting rate), not a pure constant-velocity model

A pure constant-velocity model (`F = [[1, dt], [0, 1]]`, `g` always 1) was implemented
first and then rejected after a live test exposed a real problem: over a short `dt` (a
materialized tick, minutes), extrapolating `level += rate*dt` is exactly the desired
behavior. But over a long real gap (hours, e.g. a connectivity outage), a pure
constant-velocity model extrapolates whatever `rate` was last estimated **indefinitely**
into the future. A live test — settle to a state with a small negative `rate`, then
simulate a multi-hour gap — showed the level estimate swinging from `0.88` toward `0.0`
over three 5-hour predict-only steps: communication failure turning into a *fabricated
recovery*, the mirror image of the "communication failure must not become fabricated
degradation" requirement (Phase 12 brief §27).

Decaying `rate` toward zero as the gap grows (`g -> 0`) fixes this: the level movement for
*this* step still uses the full last-known rate (short-horizon behavior is unchanged,
`g ~= 1` for `dt` << `tau`), but the rate carried into the *next* step shrinks, so a long
unobserved gap flattens out into "hold roughly where we are" rather than extrapolating a
trend forever. `rate_decay_tau_seconds` (default `3600.0`, i.e. 1 hour) is the only new
parameter this required. Covariance growth from `Q` is untouched by this and is what
separately drives `uncertainty` toward `HIGH` during the same gap.

### Why a linear KF, not an EKF (Phase 12 brief §7)

No EKF was implemented. The calibration transform above (`robust_deviation ->
normalized_evidence`) is a genuinely nonlinear function — but it is applied to the **raw
sensor feature**, before the value ever becomes the Kalman observation `z`, and it does
not depend on the hidden state `x`. Once inside the filter, the measurement model is
exactly `z = H @ x + noise` with constant `H = [1, 0]` — linear. An EKF is for when the
measurement function `h(x)` (or the transition function) is nonlinear *in the state
itself*; that never happens here. Implementing an EKF anyway would have added
linearization machinery (Jacobians) with no corresponding modeling benefit — exactly the
brief's own warning against implementing EKF "merely to make the project look more
sophisticated" (§7).

## Quality-aware updates (Phase 12 brief §9)

Uses the feature vector's own aggregate `quality_summary.state`
(`TRUSTED`/`CAUTION`/`NO_TRUSTED_DATA` — Phase 10's own vocabulary) rather than a
per-sensor eligibility Phase 10 does not currently expose per individual feature value:

- **`ELIGIBLE`** (`quality_summary.state == "TRUSTED"`): channel's `base_variance` used
  as-is.
- **`ELIGIBLE_WITH_CAUTION`** (`"CAUTION"`): every present channel's variance is
  multiplied by `caution_inflation_factor` (default `4.0`, i.e. 2x the standard
  deviation) this tick — reduces the Kalman gain, so a CAUTION-quality reading moves the
  posterior less than the same raw value would under full trust (verified directly:
  `test_caution_quality_inflates_variance_and_reduces_kalman_gain`).
- **`INELIGIBLE`**: Phase 10 already suppresses `INELIGIBLE` readings before they ever
  reach `feature_values` (a value simply becomes "missing" — `docs/FEATURE_ENGINEERING.md`),
  so this case needs no separate handling here: a missing channel is skipped (see below).

This is a deliberate scope decision, not an oversight: Phase 10's `quality_summary` is
already the point of quality integration for feature-consuming layers, and per-sensor
CAUTION/TRUSTED granularity within one tick would require a Phase 10 change, which this
phase does not make (mirrors ADR-080's precedent).

## Missing observations, prediction-only, and outages

Each configured channel is checked independently: if its feature name is in
`missing_features` (or absent/non-numeric in `feature_values`), it is simply **skipped**
this tick — never substituted with `0.0` (`test_ineligible_reading_never_substituted_with
_zero` proves this: an explicit `0.0` reading and a missing reading produce measurably
different posteriors). Available channels are applied as **sequential scalar updates**
(call `kalman.update` once per channel, feeding each call's output into the next) —
mathematically equivalent to one batched vector update with diagonal `R`, and far simpler
when the number of available channels varies tick to tick.

If **zero** channels are available this tick (below `minimum_observations`, default 1),
the estimator still runs `predict` (no `update`) and marks `prediction_only=True`.
Covariance grows via `Q` during any predict-only step, which is what naturally increases
`uncertainty` during an outage — no special-cased "outage mode" logic is needed beyond the
filter's own math. An explicit backstop (`gap.max_prediction_only_gap_seconds`, default
24h) forces `uncertainty="HIGH"` and `trend="UNKNOWN"` **only while still blind** (this
tick is also `prediction_only`) — a fresh, trusted observation that arrives right after a
long gap is allowed to restore confidence immediately, because that observation's own
Kalman-gain update has already reduced the posterior variance; forcing `HIGH` regardless
would contradict the filter's own math (a real bug found and fixed during live
verification — see the final report's "Uncertainty model" section).

## Variable dt and gap handling

`dt` is computed from real `as_of_timestamp`s (`this tick - prior tick`), never assumed
fixed. It is clamped to `[gap.min_dt_seconds, gap.max_dt_seconds]` (default `[1.0,
21600.0]`) before use — the lower bound guards a degenerate zero/negative gap; the upper
bound bounds how large a single predict step's process-noise/extrapolation jump can be for
an arbitrarily long real gap (a 30-day-old prior does not produce a 30-day single jump; it
produces one 6-hour-equivalent jump, capped).

## Uncertainty model

`uncertainty` (`LOW`/`MODERATE`/`HIGH`) is derived from the posterior `P[0][0]`
(`Var(level)`) against two configured thresholds (`uncertainty.low_max_variance`,
`uncertainty.moderate_max_variance`), with the prediction-only gap backstop described
above layered on top. This is an **explainability aid derived from the filter's own
covariance**, never confused with fault severity (Phase 12 brief §12) — a HIGH-uncertainty
NOMINAL estimate and a HIGH-uncertainty SEVERE estimate both say "trust this number less
right now," nothing about how bad the underlying condition is.

## State constraints (Phase 12 brief §13)

- `level` clipped to `level_bounds` (default `[0.0, 1.0]`) after every step.
- `rate` clipped to `[-rate_bound, rate_bound]` (default `±0.01` state-units/second) —
  the mean-reverting-rate fix above already prevents most runaway extrapolation, but this
  is a hard numerical safety net.
- Covariance terms (`P00`, `P11`) are capped at a fixed, non-tunable numerical-overflow
  guard (`1.0e6`) — purely a safety bound against unbounded growth over an arbitrarily
  long, sparsely-observed replay sequence; the `LOW`/`MODERATE`/`HIGH` reporting already
  saturates well below this.
- All arithmetic is closed-form (predict/update are polynomial; the only divisions are by
  `S = P00 + R`, guarded `> 0`, and `mad_scale`, a positive config constant) — no code path
  can produce `NaN`/`inf` from finite, valid inputs; `test_predict_then_update_stays_finite
  _over_many_iterations` runs 500 iterations and checks this directly.

## Versioning and the state-estimate contract

Every persisted `StateEstimate` row carries: `estimator_id`, `estimator_version`,
`config_version`, `feature_set`/`feature_set_version`, `feature_vector_id`,
`as_of_timestamp`, `state_value`, `state_rate`, `trend`, `uncertainty`,
`covariance_summary`, `dt_seconds`, `prediction_only`, `observations_used`,
`observations_missing`, `quality_summary` (Phase 12 brief §15-§16). Idempotency is
enforced on `(tenant_id, machine_id, state_type, as_of_timestamp, estimator_version)` — a
unique constraint plus `ON CONFLICT DO NOTHING` (mirrors Phase 10's `FeatureRepository`
pattern), so replaying the same historical window twice never duplicates rows.

## Online estimation vs. historical replay

Unlike Phase 10/11 (stateless, embarrassingly-parallel point-in-time recomputation), a
state estimate is inherently **sequential** — its posterior depends on the previous
posterior for the same `(machine, state_type, estimator_version)`.

- **Online** (`StateEstimationService.compute_and_persist_latest`, `GET
  /api/v1/state-estimation/machines/{id}/latest`): loads the most recent persisted prior
  (if any), computes the current Phase 10 `STATE_ESTIMATION_V1` feature vector via the
  unchanged `FeatureEngine`, runs one filter step for each configured state type, persists,
  returns both.
- **Historical replay** (`ReplayService`, `python -m app.state_estimation.replay
  --machine-id ... --start ... --end ...`): fetches every already-materialized
  `STATE_ESTIMATION_V1` `FeatureVector` in a time window, **sorts them ascending**, and
  walks the filter forward tick by tick, carrying the in-memory posterior between ticks
  (not re-querying the database every step). This ordering requirement — never
  parallelizable across ticks the way Phase 10/11's recomputation is — is a real
  architectural difference from every prior phase, recorded in the corresponding ADR.

Neither path ever imports `simulator` or reads a ground-truth field — see "Ground-truth
boundary" below.

## Ground-truth boundary (Phase 12 brief §1)

The estimator's only inputs are a `PriorEstimate` (its own prior output) and a
`FeatureTick` (a label-free slice of a Phase 10 `FeatureComputationResult`/`FeatureVector`
— `feature_values`, `missing_features`, `quality_summary.state`, `as_of_timestamp`, and
identifiers). There is no parameter, import, or code path through which
`restriction_factor`, `pump_efficiency`, `bearing_health`, `scenario_type`, `severity`, or
any other simulator hidden-state field could reach it.

This is checked automatically, not just documented:
`tests/state_estimation/test_ground_truth_leakage.py` (a) walks every `.py` file under
`app/state_estimation/` via `ast` and asserts none imports `simulator` (or `ml_service`),
and (b) asserts every configured observation-channel feature name — and every Phase 10
`STATE_ESTIMATION_V1` feature name, not just the configured ones — is free of a list of
forbidden ground-truth tokens (`restriction_factor`, `leakage_factor`, `pump_efficiency`,
`bearing_health`, `lifecycle_state`, `severity`, `ground_truth`, `true_value`, ...).
Mirrors `ml-service`'s Phase 11 leakage-audit approach.

## Evaluation methodology (Phase 12 brief §29-§30)

For **evaluation only**, after inference, an estimated-state series may be compared
against a simulator hidden-state **proxy** (never a feature, never an estimator input):

- Delivery proxy: `max(circuit.restriction_factor, circuit.leakage_factor, 1 -
  pump_efficiency)` across a run's circuits.
- Bearing proxy: `1 - min(bearing.health)` across a run's bearings.

This comparison lives entirely **outside** `app.state_estimation` — pure metric functions
(`MAE`, `RMSE`, Pearson correlation, trend-agreement rate, smoothness, detection lead/lag)
live in `app/state_estimation/evaluation/metrics.py`, which takes only aligned numeric
series and has no I/O and no simulator import at all; the code that reads ground truth and
builds the proxy series lives in a standalone script
(`backend/scripts/evaluate_state_estimation.py`), analogous to how `ml-service`'s
evaluation scripts live outside the trained-model package itself. Parameters (`mad_scale`,
`q_level`/`q_rate`, `rate_decay_tau_seconds`, thresholds) were chosen against HEALTHY
calibration runs only (stability, low false-trend rate) — never iteratively re-tuned
against the fault-scenario evaluation runs to make a specific number look better (Phase 12
brief §30).

## API

Tenant-scoped, mirrors Phase 11's `/ml` API shape:

- `GET /api/v1/state-estimation/machines/{machine_id}/latest` — computes + persists both
  configured state types from one shared feature vector, returns
  `{state_type: StateEstimateResponse}`.
- `GET /api/v1/state-estimation/machines/{machine_id}/history?state_type=...&start=...
  &end=...&limit=...` — read-only.
- `GET /api/v1/state-estimation/metrics` — unscoped Prometheus-text counters (see
  "Observability" below).

## Frontend

`/state-estimation` — machine selector, one card per state type (value, trend,
uncertainty, observations used/missing, dt), and a recent-history table. Not the final
Condition Intelligence UI.

## Observability

No periodic worker/container exists for Phase 12 (same on-demand-only decision as Phase
11's ADR-100 — see the corresponding ADR). `app.state_estimation.observability.METRICS`
(the existing `WorkerMetrics` renderer, reused rather than reinvented) tracks
`state_estimates_computed`, `state_estimation_failures`, `prediction_only_updates`,
`quality_suppressed_observations`, `high_uncertainty_estimates` (counters), and
`state_estimation_duration_seconds` (gauge), exposed at
`GET /api/v1/state-estimation/metrics` rather than a dedicated worker health port.

## Limitations

- **Modest, synthetic-scale calibration.** `mad_scale`/noise/threshold values were sanity
  checked against real generated HEALTHY/fault runs (see the final report), not tuned
  against a large real fleet — labeled DEMO SYNTHETIC ASSUMPTIONS throughout.
- **Machine-level, not bearing-level, granularity.** `component_id` is always `null` in
  v1: Phase 10 feature vectors are machine-scoped, not per-bearing, so
  `BEARING_CONDITION_STATE` reflects the machine's aggregate bearing-relevant evidence, not
  a specific `Bearing` row, even on a machine with multiple registered bearings.
  Bearing-level granularity would require a Phase 10 change, out of scope here.
- **No cycle-timing observation channels** (`cycle.pressure_rise_time`,
  `cycle.duration`, `cycle.success`, ...) — see "Observation model" above for why.
- **Historical eligibility/baseline staleness is inherited, not new.** Materializing
  `STATE_ESTIMATION_V1` vectors far in the past can show every `*.robust_deviation` channel
  as missing even when the underlying `.current` reading is present, because Phase 8's
  ACTIVE-baseline selection (like Phase 7's eligibility, already documented in
  `docs/FEATURE_ENGINEERING.md`) reflects *current* real-time state, not a true
  point-in-time baseline timeline. Verified live against real historical flagship telemetry
  (see the final report) — this is graceful degradation (`prediction_only=True`,
  `uncertainty=HIGH`), never a crash or a fabricated value, but it does mean deep
  historical replay windows may show little real signal until this pre-existing limitation
  is addressed in a later phase.
- **No periodic retraining/re-calibration loop.** Config is versioned and static per
  `config_version`; nothing in Phase 12 auto-adjusts thresholds from live data.
- **Independent from Phase 11 ML by design**, not by omission — see "ML independence"
  below.

## ML independence (Phase 12 brief §31)

State estimation does not consume Phase 11 classifier probabilities or anomaly scores as
inputs, and Phase 11's `ml-service`/`app.ml` are not imported anywhere in
`app.state_estimation` (checked by the same leakage test). Rules (Phase 9), ML (Phase 11),
and state estimation (Phase 12) are kept as three structurally independent evidence
producers so Phase 13 Condition Intelligence can genuinely combine distinct sources rather
than one evidence stream disguised as three.
