# Maintenance Workflow — Phase 17

## Purpose

`app.maintenance` turns an `Incident` under investigation into a structured,
**human-controlled** maintenance workflow. No physical maintenance action is ever
executed automatically (CLAUDE.md "Workflow Intelligence" boundary) — this package only
ever records what a human recommended, planned, performed, or found.

## Maintenance lifecycle

Seven states (`app.domain.enums.MaintenanceState`): `REVIEW_REQUIRED`, `NOT_STARTED`,
`PLANNED`, `IN_PROGRESS`, `AWAITING_VERIFICATION`, `COMPLETED`, `CANCELLED`. A case is
created at `REVIEW_REQUIRED` when the underlying `DecisionAssessment.human_review_
required` is true (the common case — most real recommended actions are physical
inspections), else `NOT_STARTED`. `plan()` → `PLANNED`, `start()` → `IN_PROGRESS`,
recording a physical `MaintenanceAction` → `AWAITING_VERIFICATION`, `complete()` →
`COMPLETED`. At most one non-terminal case may exist per incident
(`uq_maintenance_case_active_incident`) — `MaintenanceService.create_case_for_incident()`
is idempotent.

## Checklist model

Deterministic, template-based (Phase 17 brief §17.5) — **no RAG, no LLM**.
`app.maintenance.checklist_templates.resolve_checklist(recommended_action)` is a plain
dict lookup keyed by `RecommendedAction`, falling back to a generic template for any
unmapped action. The resolved checklist is snapshotted onto `MaintenanceCase.checklist`
as `[{text, completed}, ...]` at creation time — embedded JSONB rather than a separate
`inspection_checklist` table, for the same single-table-over-child-table rationale
`RuleFinding` already established (ADR-078, see ADR-129). Wording is generic and
safety-conscious; these are demo workflow templates, never proprietary procedures.

## Technician finding model

`TechnicianFindingResult` (Phase 17 brief §17.6): `CONFIRMED`, `NOT_CONFIRMED`,
`PARTIALLY_CONFIRMED`, `DIFFERENT_ISSUE_FOUND`, `UNABLE_TO_VERIFY` — deliberately not a
binary confirm/deny (§17.12). `TechnicianFinding` rows are append-only; a case can
accumulate multiple findings over its life.

## Maintenance action model

`MaintenanceActionType` (Phase 17 brief §17.7): `INSPECTED`, `CLEANED`, `REFILLED`,
`COMPONENT_REPLACED`, `ADJUSTMENT_RECOMMENDED`, `NO_ACTION_REQUIRED`, `ESCALATED`.
Recording an action is a record of what a human did, never a system-issued physical
command. A "physical" action (`CLEANED`/`REFILLED`/`COMPONENT_REPLACED`/
`ADJUSTMENT_RECOMMENDED`) moves the case to `AWAITING_VERIFICATION`; `NO_ACTION_REQUIRED`/
`INSPECTED`/`ESCALATED` do not, since nothing requires physical re-verification.

## Verification and completion

`MaintenanceService.complete()` requires an explicit `FeedbackClassification` AND
performs a real, fresh `ConditionEngine.assess()` re-check of the machine, recording its
result as `FeedbackRecord.post_action_condition_type` — the case is never marked
`COMPLETED` solely because an endpoint was called (Phase 17 brief §17.8, ADR-133).
Completion also resolves the linked `Incident` (never closes it — closing remains an
explicit separate human action).

## Feedback loop

`FeedbackClassification` (Phase 17 brief §17.9, matching CLAUDE.md's vocabulary exactly):
`TRUE_POSITIVE`, `FALSE_POSITIVE`, `MISSED_FAILURE`, `INCONCLUSIVE`. One `FeedbackRecord`
per completed case, preserving pointers to the original `ConditionAssessment`/
`DecisionAssessment`/`Incident` — **the original intelligence result is never erased**,
even for a `FALSE_POSITIVE` outcome (§17.10). Recording feedback **never** automatically
retrains an ML model (ADR-131) — it is an audit/learning record for a future, explicitly
human-triggered evaluation phase, matching the already-accepted no-auto-retraining rule
from Phase 11/CLAUDE.md.

## API

- `POST /api/v1/maintenance/cases` (body: `incident_id`) — idempotent create
- `GET /api/v1/maintenance/cases`, `GET .../{id}`, `.../findings`, `.../actions`,
  `.../feedback`
- `POST .../{id}/plan`, `.../start`, `.../finding`, `.../action`, `.../complete`,
  `.../cancel`
- `POST .../{id}/cmms-draft` — see `docs/CMMS_INTEGRATION.md`
- `GET /api/v1/maintenance/cases/metrics`

## Known limitations

`checklist.completed` per-item flags exist in the contract but are not yet toggled by any
endpoint (no per-item "check off" API in this sprint) — the checklist is currently
presented and recorded as a whole; per-item completion is a natural, small future
extension. No automatic reminder/escalation for a case stuck in `PLANNED`/`IN_PROGRESS`
past its window.
