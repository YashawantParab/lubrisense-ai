# Decision Intelligence — Phase 14

## Purpose

`app.decision_intelligence` answers **WHAT SHOULD I DO?** by turning a Phase 13
`ConditionAssessment` (and its associated Phase 15 forecasts) into a persisted, versioned
`DecisionAssessment` — the top of the intelligence chain, and the only layer whose output is
meant to eventually trigger a human maintenance action. `DecisionEngine` never controls
machinery, never changes a lubrication quantity, never overrides a PLC, and never
auto-closes anything; every physical action carries `human_review_required=true` (see
"Human-review boundary" below).

`DecisionEngine.decide_for_machine()` triggers the *full* fresh chain on every call — a real
`ConditionEngine.assess()` and a real `PrognosticEngine.forecast_machine()` — rather than
reading whatever the most recently persisted condition/forecast happen to be, so the decision
is always internally consistent with the evidence it cites (`condition_assessment_id`,
`prognostic_assessment_id` always point at rows produced in the same call).

## Decision priority model

Four levels (`app.domain.enums.DecisionPriority`: `MONITOR`/`PLANNED`/`HIGH`/`URGENT`), built
as an explainable integer tier (0-3, `severity_priority_tier`) rather than an opaque score:

1. Base tier from `ConditionAssessment.severity` (`INFO`→0 … `CRITICAL`→3)
2. `+1` if `lifecycle_state == PERSISTENT` (the same condition has recurred across multiple
   assessments — not a one-off)
3. `+1` if `Machine.criticality` is `HIGH`/`CRITICAL` — **only** for genuine fault-pattern
   condition types (see "Criticality handling" below)
4. `+1` if any prognostic forecast reports an imminent threshold crossing (`status=="OK"` and
   `threshold_crossing_seconds <= imminent_crossing_seconds`, default 21600s / 6h)

Tier is clamped to `[0, 3]` and mapped back to a priority name
(`policy.priority_for_tier`/`tier_for_priority`). `recommended_window` follows priority
directly (`priority_window_map`: `MONITOR→MONITOR`, `PLANNED→NEXT_PLANNED_MAINTENANCE`,
`HIGH→WITHIN_HOURS`, `URGENT→NOW`).

## Criticality handling boundary

`decision_synthesis._NON_FAULT_TYPES = {NORMAL_OPERATION, INSUFFICIENT_EVIDENCE,
SENSOR_OR_DATA_QUALITY_LIMITATION, AMBIGUOUS_CONDITION}`. These four condition types never
enter the severity-tier/adjustment path at all — criticality, persistence, and forecast
urgency can shift priority *within* an already-real fault pattern, but can never manufacture
a fault-pattern decision out of a genuinely normal, inconclusive, quality-limited, or
conflicting condition. Verified by `test_criticality_never_elevates_normal_operation` /
`test_criticality_never_elevates_ambiguous_condition` in
`tests/decision_intelligence/test_decision_synthesis.py`.

## Recommended action model

`condition_action_map` (12 entries, one per `ConditionType`) maps directly to a safe, generic
`RecommendedAction` — e.g. `DEVELOPING_RESTRICTION_PATTERN`→`INSPECT_LUBRICATION_PATH`,
`INDEPENDENT_BEARING_CONDITION`→`INSPECT_BEARING` (never blamed on lubrication),
`PUMP_PERFORMANCE_DEGRADATION`→`CHECK_PUMP`, `INSUFFICIENT_EVIDENCE`→
`REQUEST_ADDITIONAL_MEASUREMENT`, `SENSOR_OR_DATA_QUALITY_LIMITATION`→`VERIFY_SENSOR`,
`NORMAL_OPERATION`→`CONTINUE_MONITORING`. All actions are inspection/verification/monitoring
requests — `non_physical_actions` (`CONTINUE_MONITORING`, `VERIFY_SENSOR`,
`REQUEST_ADDITIONAL_MEASUREMENT`) never require human review; every other (physical
inspection) action does.

## Human-review boundary

`human_review_required = recommended_action not in non_physical_actions`. This is a
structural gate, not a per-case judgment call — any action that sends a technician to
physically inspect equipment requires human review before being acted on; only pure
monitoring/verification/measurement requests can be surfaced without it.

## Confidence and risk language

`DecisionAssessment.confidence` is always exactly `ConditionAssessment.confidence` — a
decision can never claim more certainty than the condition it is based on
(`test_decision_confidence_never_exceeds_condition_confidence`). `risk_if_deferred` uses
`risk_language` (12 entries, one per condition type), written in cautious, non-causal wording
("evidence is consistent with...", "may reduce...", never "will fail" or "is caused by") per
CLAUDE.md's product-story guardrails.

## Explainability contract

`DecisionAssessment.evidence` always carries: `what_should_i_do`, `why`, `when`,
`risk_if_deferred`, `confidence`, `based_on_condition_id`, `missing_data` (explicit gaps —
e.g. "No reliable forecast is available to inform urgency."). `limitations` mirrors
`missing_data` as a top-level list for direct frontend/API consumption.

## Decision lifecycle — supersede, never overwrite

Four states (`app.domain.enums.DecisionLifecycle`: `ACTIVE`/`SUPERSEDED`/`EXPIRED`/
`RESOLVED`). `DecisionAssessmentRepository.insert_and_supersede_prior()` is the one
deliberate exception to this platform's append-only-history pattern: before inserting a new
decision, it runs a real `UPDATE` transitioning the machine's previously-`ACTIVE` decision to
`SUPERSEDED` — the prior decision is never deleted, and `history` always shows the full
lifecycle trail. `expires_at` is set from `expiry_seconds_by_priority` (`URGENT`→2h,
`HIGH`→8h, `PLANNED`→3d, `MONITOR`→7d) for downstream staleness handling; nothing in this
phase automatically transitions a row to `EXPIRED`/`RESOLVED` — that belongs to Phase 16/17's
incident/workflow lifecycle.

## API

- `GET /api/v1/decisions/machines/{id}/latest` — triggers the full fresh chain (condition +
  prognostics + decision), supersedes the prior `ACTIVE` decision, returns the new one
- `GET /api/v1/decisions/machines/{id}/history` — read-only, includes superseded rows
- `GET /api/v1/decisions/metrics` — unscoped Prometheus-text counters, including
  `intelligence_processing_errors`/`intelligence_processing_duration` since `DecisionEngine`
  is the top of the chain that triggers Condition + Prognostics
- `GET /api/v1/intelligence/machines/{id}` — combined read view (`{condition, prognostics,
  decision}`) from one `DecisionEngine` call, for a single mutually-consistent snapshot;
  persistence boundaries stay separate (three real tables), this is purely a response shape

## Known limitations

Priority/action/risk-language mappings are demo-scale YAML defaults
(`decision_intelligence_v1.yaml`), not validated industrial policy. No automatic
expiry/resolution sweep exists yet — `expires_at` is computed but not enforced by a worker.
No CMMS/work-order integration yet (Phase 17).
