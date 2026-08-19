# Product / North-Star Metrics (Phase 22)

## Purpose

Measure whether the product actually helps — detecting meaningful lubrication issues
early enough to act — using only what this reference platform's persisted data can
honestly support. Every metric declares its `MetricProvenance`
(`MEASURED_PLATFORM_METRIC` / `DEMO_ESTIMATE` / `CONFIGURED_TARGET`); the three are never
mixed into one number (CLAUDE.md "Customer / Business Thinking").

## North Star

**"Percentage of meaningful lubrication issues detected with actionable lead time."**

Computed by `app.product_metrics.north_star.compute_north_star()`:

- **Denominator** — every `FeedbackRecord` a technician has classified `TRUE_POSITIVE`
  or `MISSED_FAILURE`: every case a human confirmed was a real issue, whether or not the
  platform gave useful lead time.
- **Numerator** — of those, the `TRUE_POSITIVE` ones whose `MaintenanceCase
  .recommended_window` was **not** `NOW` — the platform's own decision output gave the
  technician a planning window rather than only flagging an emergency already underway.

```
north_star = count(TRUE_POSITIVE AND recommended_window != NOW)
             ---------------------------------------------------
             count(TRUE_POSITIVE) + count(MISSED_FAILURE)
```

Labelled `DEMO_ESTIMATE` — see "Known limitation" below.

**Why `MISSED_FAILURE` only affects the denominator:** `FeedbackClassification
.MISSED_FAILURE` (Phase 17) is recorded against a `MaintenanceCase` that *did* exist —
i.e., an incident was raised and investigated, but the technician's finding was that a
failure had already occurred by the time it was addressed. That is exactly "a meaningful
issue, not detected with useful lead time" — it belongs in the denominator (it was real)
but never the numerator (it wasn't caught in time).

### Known limitation — the population this can measure

This reference platform has no external ground-truth failure feed, so it structurally
**cannot** count a failure that occurred with *no* incident ever raised at all (a true
false-negative against the physical world). The North Star here is therefore computed
only over incidents the platform *did* raise and a technician *did* investigate — a
conservative, honest proxy, not a full-population detection rate. This is why every
result is returned as `DEMO_ESTIMATE`/`DEMO / SYNTHETIC EVALUATION`, never as validated
industrial performance (CLAUDE.md "Customer / Business Thinking").

## Supporting metrics

`app.product_metrics.supporting_metrics.compute_supporting_metrics()` — all
`MEASURED_PLATFORM_METRIC`:

| metric_id | Definition |
|---|---|
| `coverage.instrumented_asset_coverage` | machines with >=1 sensor / total machines |
| `coverage.connected_asset_coverage` | machines that have ever produced telemetry / total machines |
| `coverage.telemetry_availability` | machines with telemetry in the trailing freshness window / total machines |
| `feedback.true_positive_confirmation_rate` | TRUE_POSITIVE feedback / all feedback |
| `feedback.false_positive_rate` | FALSE_POSITIVE feedback / all feedback |
| `feedback.useful_incident_rate` | (TRUE_POSITIVE + MISSED_FAILURE) / all feedback |
| `incidents.unresolved_burden` | count of incidents not RESOLVED/CLOSED |
| `incidents.mean_acknowledge_time_minutes` | mean(acknowledged_at − first_detected_at) |
| `maintenance.mean_resolution_time_minutes` | mean(completed_at − created_at), COMPLETED cases |
| `decisions.actionable_warning_lead_time_rate` | TRUE_POSITIVE with non-NOW window / all TRUE_POSITIVE |
| `workflow.decision_to_maintenance_conversion` | maintenance cases created / incidents created |
| `workflow.cmms_draft_creation_rate` | CMMS work-order drafts / maintenance cases |
| `assistant.usage_sessions` / `usage_messages` | raw `AgentSession`/`AgentMessage` counts |
| `knowledge.insufficient_documentation_rate` | assistant answers containing the exact insufficient-documentation fallback / all assistant answers |
| `knowledge.approved_knowledge_coverage` | APPROVED documents visible to this tenant / all visible documents |

A ratio metric with a zero denominator returns `value=None` with a
`data_completeness_note` — never a fabricated zero (CLAUDE.md "return random health
scores" prohibition extended to metrics).

## Metric provenance (§22.3)

Every `Metric` carries: `metric_id`, `name`, `definition`, `window_description`, `value`,
`unit`, `numerator`, `denominator`, `provenance`, `source`, `scope`, `calculated_at`,
`data_completeness_note`. This is the full record, not a bare number — a client can
always show *why* a metric has the value it does.

## Measured vs. demo/estimated

- **`MEASURED_PLATFORM_METRIC`** — every supporting metric; a direct SQL aggregate over
  this tenant's own persisted rows.
- **`DEMO_ESTIMATE`** — the North Star, because its denominator population is itself an
  honest-but-incomplete proxy (see above).
- **`CONFIGURED_TARGET`** — reserved for a future operator-set goal value (e.g. "target
  90% actionable-lead-time rate"); no such value is computed yet, so no metric currently
  returns this provenance — the enum value exists so a future addition has a home without
  a schema change.

## API

- `GET /api/v1/product-metrics` — North Star + all supporting metrics.
- `GET /api/v1/product-metrics/north-star` — North Star alone.

Both require `Permission.METRICS_READ` (Phase 24), tenant-scoped.

## A real bug this sprint's own testing caught

An early version of `coverage.instrumented_asset_coverage` called the shared
`instrumented_machine_ids_subquery()` helper without a tenant filter, returning a count
across **every tenant in the database** rather than the current one — a real cross-tenant
leakage bug in a brand-new metric, caught immediately by
`test_instrumented_asset_coverage_reflects_real_sensor` (the count came back as 625, not
1, against this session's shared dev database). Fixed by first resolving the current
tenant's own machine ids and passing them explicitly into the subquery — the same pattern
`app.customer_services.service` already used correctly. Documented as ADR-156.
