# Prognostics — Phase 15

## Purpose

`app.prognostics` answers **WHAT MAY HAPPEN NEXT?** by extrapolating Phase 12's own posterior
Kalman state (`[level, rate]`) forward in time. It is deliberately **not** a full
remaining-useful-life (RUL) model, a survival model, or a re-fit trend regression — it is a
lightweight, explainable, CPU-cheap linear projection of evidence the platform has already
computed, with uncertainty that only ever grows with weaker evidence. Output is condition
EVIDENCE for Phase 14, never a certainty ("failure will occur" is prohibited language
everywhere in this package — see `_risk_language`/cautious-wording checks in tests).

## Why extrapolate the existing posterior rather than re-fit a trend

Phase 12's Kalman filter already estimates `state_rate` (the `[level, rate]` posterior) at
every tick from the same evidence a separate trend-fit would use. Re-fitting a second,
independent trend model over `StateEstimate` history would (a) duplicate work the estimator
already does, (b) risk disagreeing with the estimator's own trend classification
(`STABLE`/`DETERIORATING`/`IMPROVING`/`UNKNOWN`), and (c) add a second tunable model surface
with no additional physical justification. `services/forecast.py` instead takes the current
row's `state_value`/`state_rate` and projects `level + rate * horizon_seconds`, clipped to the
Phase 12 state bounds `[0.0, 1.0]`.

## Horizons

Three fixed, configurable horizons (`app.domain.enums.ForecastHorizon`,
`prognostics_v1.yaml`): `ONE_HOUR` (3600s), `SIX_HOURS` (21600s), `TWENTY_FOUR_HOURS`
(86400s). One `PrognosticAssessment` row is persisted per `(state_type, horizon)` pair per
call — six rows per machine per assessment (2 state types × 3 horizons).

## Data sufficiency and `NO_RELIABLE_FORECAST`

`data_sufficiency_check(current, history, policy)` returns `(sufficient, reasons)` before any
extrapolation is attempted. A forecast is downgraded to `status=NO_RELIABLE_FORECAST` (rather
than a fabricated number) when:

- fewer than `data_sufficiency.minimum_history_count` (default 3) prior estimates exist
- the current estimate is `prediction_only` (Phase 12 has no recent real observation)
- current uncertainty is `HIGH`
- the sign of `state_rate` has flipped across recent history (`rate_sign_flip_makes_
  unstable=true` — an oscillating trend cannot be linearly extrapolated in good faith)

`limitations` on the persisted row always explains *why* in plain language when this happens.

## Forecast uncertainty

Uncertainty (`app.domain.enums.` shared `StateUncertaintyCategory` values) is inherited from
and never better than the current `StateEstimate`'s own uncertainty, and is escalated further
whenever history is short or the trend looks unstable — uncertainty can only increase relative
to the underlying state estimate, never manufactured as more confident than the evidence it is
built from.

## Threshold-crossing model

A crossing time is only ever reported when all three hold: `rate > 0` (moving toward the
configured `degradation_threshold`, default 0.7), `level < threshold` (hasn't crossed yet),
and the computed `seconds_to_cross` falls within `max_crossing_horizon_seconds` (7 days,
configurable) — otherwise `estimated_threshold_crossing_time=null`. Language is always
"estimated crossing under current trend if it continues", never "will fail" — enforced by
`risk_language`/wording review in Phase 14's decision layer, which consumes this field only as
one signal among several (`imminent_crossing_seconds` tier bump), never as the sole driver of
urgency.

## Post-hoc evaluation only

Like Phase 12, no forecast ever reads a Phase 4 simulator ground-truth field or a future
telemetry row at inference time — `services/forecast.py` has no import of `simulator` or any
future-dated query. Ground-truth comparison (when performed) happens strictly after the fact,
outside the inference path, mirroring Phase 12's `evaluation/metrics.py` boundary.

## API

- `GET /api/v1/prognostics/machines/{id}/latest` — computes + persists a fresh forecast set
  for every configured `(state_type, horizon)` pair from the current Phase 12 state estimate;
  returns `[]` (not an error) for a machine with no state estimates yet
- `GET /api/v1/prognostics/machines/{id}/history` — read-only, filterable by `state_type`
- `GET /api/v1/prognostics/metrics` — unscoped Prometheus-text counters

## Persistence

`PrognosticAssessment` (migration `13d670ebdb0c`) is append-only, one row per
`(state_type, horizon)` per call. `PrognosticAssessmentRepository.insert()` calls
`session.refresh()` after flush for the same enum-hydration reason documented in
`docs/CONDITION_INTELLIGENCE.md`.

## Known limitations

Linear extrapolation cannot anticipate a future regime change (e.g. a sudden blockage that
hasn't started yet) — by design, since a genuinely novel future event has no evidence to
extrapolate from. Horizon/threshold/data-sufficiency values are demo-scale YAML defaults, not
validated industrial thresholds. Machine-level granularity only, matching Phase 12.
