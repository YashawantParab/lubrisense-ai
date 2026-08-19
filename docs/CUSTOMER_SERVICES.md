# Customer / Fleet Services (Phase 21)

## Purpose

Above individual-machine intelligence, an operator needs a fleet/customer/site-level
answer to: *how is my install base doing, where is visibility limited, and where does a
human need to look?* `app.customer_services.CustomerOverviewService` answers this
directly from persisted platform data — no invented ROI, no fabricated health score.

## Architecture

`backend/app/customer_services/`:

- `models.py` — `AssetCoverageSummary`, `OperationalSummary`, `ServiceBurdenSummary`,
  `CustomerOverview`, `SiteOverview`, `FleetOverview` (frozen dataclasses).
- `policy.py` — `CustomerServicePolicy` (telemetry freshness window, minimum visibility
  ratio, recent-findings window) — a plain, documented threshold set, not a black box.
- `service.py` — `CustomerOverviewService`, aggregating over the existing asset hierarchy
  (`Tenant → CustomerAccount → Site → Plant → ProductionLine → Machine`) and every
  intelligence/workflow table already built in Phases 6–20 (`Sensor`, `Telemetry`,
  `ConditionAssessment`, `MLInferenceResult`, `StateEstimate`, `QualityIssue`, `Incident`,
  `MaintenanceCase`, `FeedbackRecord`, `TechnicianFinding`).

Every number is a real SQL aggregate scoped to `tenant_id` (and, for customer/site
overviews, further scoped to that customer's/site's machine ids). Nothing here is
demo/estimated — commercial ROI and adoption-target values live in `app.product_metrics`
(Phase 22) instead, explicitly labelled there.

## Asset coverage

`AssetCoverageSummary` reports, per scope:

- `total_machines`
- `instrumented_machines` — machines with >=1 `Sensor` attached anywhere in their
  subtree (directly, via a `Bearing`, or via their `LubricationSystem`) — see
  `instrumented_machine_ids_subquery()`.
- `machines_with_recent_telemetry` — machines with a `Telemetry` row within
  `telemetry_freshness_window_minutes` (default 60).
- `machines_with_condition_assessment` / `_ml_result` / `_state_estimate` — coverage of
  each intelligence layer.
- `machines_with_open_data_quality_issues` — machines with an `ACTIVE`/`RECOVERING`
  `QualityIssue`.

**"Instrumented" and "reporting" are deliberately different signals.** A machine can have
a sensor attached but no telemetry in the freshness window (never commissioned, gateway
down, decommissioned) — that machine is correctly treated as visibility-degraded, not
healthy, even though it has instrumentation. See the test
`test_instrumented_machine_with_no_telemetry_yet_is_degraded_visibility`.

## Customer operational status

`CustomerOperationalStatus` — `HEALTHY` / `ATTENTION_REQUIRED` / `DEGRADED_VISIBILITY` /
`MAINTENANCE_ACTIVE` / `UNKNOWN` — is a deliberately cautious **categorical precedence
policy**, not an opaque numeric score (CLAUDE.md "Avoid arbitrary opaque scoring if a
categorical policy is sufficient"). `_classify_status()` evaluates, in order, the most
severe condition first:

1. **`UNKNOWN`** — zero machines registered. Never silently reported as `HEALTHY`.
2. **`ATTENTION_REQUIRED`** — any open incident at `HIGH`/`CRITICAL` severity or
   `HIGH`/`URGENT` priority. Takes precedence over visibility gaps: a live critical
   incident matters more than an instrumentation gap elsewhere in the fleet.
3. **`DEGRADED_VISIBILITY`** — instrumentation coverage ratio or telemetry freshness
   ratio below `minimum_visibility_ratio` (default 50%). Catches both "never
   instrumented" and "instrumented but not currently reporting."
4. **`MAINTENANCE_ACTIVE`** — no attention-required incidents, adequate visibility, but
   >=1 open `MaintenanceCase` — normal planned work in progress.
5. **`HEALTHY`** — none of the above.

Every `CustomerOverview`/`SiteOverview` carries `status_reasons`: a short, human-readable
explanation of exactly why that status was assigned, not just the enum value.

## Service burden

`ServiceBurdenSummary` — `open_incidents`, `incidents_per_monitored_machine`,
`open_maintenance_cases`, `unresolved_maintenance_cases`,
`false_positive_feedback_count`, `true_positive_feedback_count`,
`mean_acknowledge_time_minutes`, `mean_resolution_time_minutes`. All real aggregates over
`Incident`/`MaintenanceCase`/`FeedbackRecord`. No fabricated monetary cost anywhere — a
mean-resolution-time number is genuinely measured minutes, not an estimated dollar
figure.

## API

- `GET /api/v1/customers/{customer_account_id}/overview`
- `GET /api/v1/sites/{site_id}/overview`
- `GET /api/v1/fleet/overview`

All three require `Permission.METRICS_READ` (Phase 24) and are tenant-scoped via the
existing `X-Tenant-ID` mechanism.

## Known limitations

- Fleet-level `customers_by_status` recomputes each customer's coverage/operations
  separately (O(customers) queries) — fine at demo scale, would want a single grouped
  query at real fleet scale.
- `incidents_per_monitored_machine` divides by *instrumented* machines, not *all*
  machines — a fleet with mostly-uninstrumented machines will show a misleadingly high
  ratio; this is called out in the field's own docstring, not hidden.
