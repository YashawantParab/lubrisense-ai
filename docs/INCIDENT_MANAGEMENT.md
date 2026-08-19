# Incident Management — Phase 16

## Purpose

`app.incidents` converts repeated Condition/Decision evaluations into **one coherent
incident per evolving operational problem**, never one row per evaluation cycle. It never
invents new evidence — every incident is a correlation and lifecycle wrapper around
already-persisted Phase 13/14/15 evidence (`ConditionAssessment`, `DecisionAssessment`,
`PrognosticAssessment`, and their underlying `RuleFinding`/`MLInferenceResult`/
`StateEstimate` ids).

## Correlation model

Correlation is **explainable, never opaque ML clustering** (Phase 16 brief §16.4).
`app.incidents.services.correlation.build_correlation_key(machine_id, component_id,
family)` produces a deterministic string; `family_for_condition_type()` maps each real
fault-pattern `ConditionType` to a coarser family (`LUBRICATION_DELIVERY` or
`BEARING_CONDITION`, `incident_correlation_v1.yaml`). Two condition types in the same
family (e.g. `DEVELOPING_RESTRICTION_PATTERN` → `DELIVERY_BLOCKAGE_PATTERN` as a
restriction worsens) correlate into the same open incident; two different families always
produce separate incidents.

`NORMAL_OPERATION`/`INSUFFICIENT_EVIDENCE`/`SENSOR_OR_DATA_QUALITY_LIMITATION`/
`AMBIGUOUS_CONDITION` never create or update an incident on their own — the identical
fault-vs-non-fault boundary Phase 14 established (ADR-119), reused one layer up.

At most one non-terminal incident may exist per `(tenant, machine, correlation_key)` at a
time — enforced by a database-level partial unique index
(`uq_incident_active_correlation_key`), the same mechanism `RuleFinding` already uses for
its own active-scope idempotency (ADR-078).

## Incident lifecycle

Eight states (`app.domain.enums.IncidentState`): `DETECTED`, `OPEN`, `ACKNOWLEDGED`,
`INVESTIGATING`, `ACTION_PLANNED`, `RESOLVED`, `CLOSED`, `REOPENED`. Transitions are
explicitly validated (`app.incidents.services.lifecycle.validate_transition`) —
`IncidentService.evaluate_machine()` creates new incidents directly at `OPEN` (real
confirmed fault evidence, never a speculative `DETECTED` pre-triage stage — see ADR-126).
`CLOSED` is always an explicit human action (`POST /incidents/{id}/close`), never
triggered automatically by recovery.

## Recovery

A fresh `NORMAL_OPERATION` result resolves every currently-open incident for that
machine. `INSUFFICIENT_EVIDENCE`/`SENSOR_OR_DATA_QUALITY_LIMITATION`/
`AMBIGUOUS_CONDITION` results leave existing open incidents untouched — evidence being
momentarily unclear is not the same as confirmed resolution.

## Incident timeline

`IncidentEvent` (append-only, never mutated) records every meaningful transition:
`INCIDENT_CREATED`, `EVIDENCE_ADDED`, `SEVERITY_CHANGED`, `PRIORITY_CHANGED`,
`ACKNOWLEDGED`, `INVESTIGATION_STARTED`, `ACTION_PLANNED`,
`TECHNICIAN_FINDING_RECORDED`, `RESOLVED`, `CLOSED`, `REOPENED`.

## Provenance

Every `Incident` accumulates (never replaces) the ids of every `ConditionAssessment`/
`DecisionAssessment`/`PrognosticAssessment`/`RuleFinding`/`MLInferenceResult`/
`StateEstimate` that contributed evidence, so the full evidence chain behind an incident
is always reconstructable.

## API

- `GET /api/v1/incidents` — list, filterable by `machine_id`/`state`
- `POST /api/v1/incidents/machines/{id}/evaluate` — triggers the full fresh Phase 14
  decision chain and correlates the result; returns `null` when no incident is warranted
- `GET /api/v1/incidents/{id}`, `GET /api/v1/incidents/{id}/timeline`
- `POST /api/v1/incidents/{id}/acknowledge` / `start-investigation` / `resolve` /
  `close` / `reopen`
- `GET /api/v1/incidents/metrics`

## Known limitations

Phase 13's `ConditionAssessment` is single-hypothesis per call (one winning
`condition_type`, or `AMBIGUOUS_CONDITION`) — two genuinely simultaneous independent
faults are represented as two incidents only across two temporally-separate evaluations
whose dominant evidence differs, not within one fused assessment (see
`docs/CONDITION_INTELLIGENCE.md` §13.10 delivery+bearing coexistence handling). No
automated periodic re-evaluation worker exists yet — incidents are only (re)computed
on-demand via `/evaluate` (ADR-124), matching Phase 11-15's own on-demand precedent.
