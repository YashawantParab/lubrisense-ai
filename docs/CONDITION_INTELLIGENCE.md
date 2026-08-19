# Condition Intelligence — Phase 13

## Purpose

`app.condition_intelligence` answers **WHAT IS HAPPENING?** for one machine, by synthesizing
already-persisted evidence from three independent, structurally-separate layers:

- Phase 9 `RuleFinding` — deterministic engineering rules
- Phase 11 `MLInferenceResult` — anomaly/classification models, filtered by lifecycle status
- Phase 12 `StateEstimate` — Kalman-filtered lubrication-delivery/bearing-condition state

Plus Phase 7 `SensorQualityState` for quality-first gating.

Output is a persisted, versioned `ConditionAssessment` — a **synthesis of evidence**, never
a diagnosis asserted as physical fact and never a maintenance decision (that's Phase 14).
`ConditionEngine` never imports `simulator`, never reads a Phase 4 scenario label, and never
reads `ml_service`/`app.ml` output as ground truth — only real, persisted, already-computed
rows produced by earlier phases.

## Condition taxonomy

Twelve values (`app.domain.enums.ConditionType`), deliberately cautious and non-diagnostic:

`NORMAL_OPERATION`, `LUBRICATION_DELIVERY_DEGRADATION`, `DEVELOPING_RESTRICTION_PATTERN`,
`DELIVERY_BLOCKAGE_PATTERN`, `POSSIBLE_LEAKAGE_PATTERN`, `PUMP_PERFORMANCE_DEGRADATION`,
`LOW_LUBRICANT_AVAILABILITY`, `BEARING_CONDITION_DEGRADATION`,
`INDEPENDENT_BEARING_CONDITION`, `SENSOR_OR_DATA_QUALITY_LIMITATION`,
`INSUFFICIENT_EVIDENCE`, `AMBIGUOUS_CONDITION`.

`LUBRICATION_DELIVERY_DEGRADATION` and `BEARING_CONDITION_DEGRADATION` are deliberately
generic — Phase 12's Kalman filters are fault-agnostic by design (ADR-103) and can only ever
vote a generic hint. `synthesis._GENERIC_TO_SPECIFIC_FAMILY` treats these as corroborating
evidence for a more specific sibling hypothesis (e.g. `DEVELOPING_RESTRICTION_PATTERN`) when
one is present, rather than as a competing hypothesis — see "Evidence-hierarchy weighting"
below.

## Evidence sources and strength tiers

Every piece of evidence becomes an `EvidenceItem(source_type, source_id, strength,
condition_hint, description, severity)`. Strength is one of four explainable tiers, never an
opaque numeric weight:

- `STRONG` — a confirmed (not `CANDIDATE`) rule finding with a direct condition mapping
- `SUPPORTING` — a validated ML classification at MODERATE/HIGH confidence, or a trustworthy,
  meaningfully-deteriorating (or stable/normal) state estimate
- `WEAK` — a `CANDIDATE` rule finding, an unmapped rule finding, a low-confidence validated
  ML result, or an untrustworthy (prediction-only / HIGH-uncertainty) state estimate
- `EXPERIMENTAL` — any ML result from a model whose registry lifecycle status is not
  VALIDATED/STAGING/PRODUCTION (see "ML lifecycle" below)

`synthesis._TALLIED_STRENGTHS` only counts `STRONG`/`SUPPORTING`/`EXPERIMENTAL` votes toward
establishing a condition; `WEAK` evidence is recorded (for explainability) but never tips the
outcome on its own.

## ML lifecycle / trust handling

`ConditionEngine._evidence_from_ml_result` cross-checks each `MLInferenceResult` against the
live `ml_service` registry (`app.ml.registry.get_model_registry()`). A model not at
VALIDATED/STAGING/PRODUCTION status is tagged `EXPERIMENTAL` regardless of its own reported
confidence. `synthesis._single_hypothesis_result` requires at least one non-EXPERIMENTAL vote
before a fault condition can be independently established — an EXPERIMENT-status model can
corroborate an already-established hypothesis but can never manufacture one alone.
Isolation-Forest-style anomaly results are fault-agnostic by construction (`condition_hint=
None`) — they can corroborate "something is abnormal" but never hint which `ConditionType`.

## Confidence model

Categorical only (`LOW`/`MODERATE`/`HIGH`, `app.domain.enums.ConditionConfidence`) — never a
fabricated percentage. Approximate rule of thumb (`synthesis._confidence_for`):

- `HIGH` — a `STRONG` vote corroborated by at least one other independent source
- `MODERATE` — a single `STRONG` vote alone, or two-or-more independent `SUPPORTING` votes
- `LOW` — a single `SUPPORTING` vote, an `INSUFFICIENT_EVIDENCE`/`AMBIGUOUS_CONDITION` result,
  or any result gated by data quality

## Conflicting-evidence handling

When two or more *non-generic, non-corroborating* hypotheses each collect a tallied vote,
`synthesize()` returns `AMBIGUOUS_CONDITION` rather than arbitrarily picking one — the
evidence-summary lists every competing hypothesis and both `supporting_evidence` sets, and
`recommended_next_evidence` asks for the specific corroboration needed to resolve it. Verified
live in Docker against a real machine whose rule findings genuinely disagreed (one CYCLE_
COMPLETION_FAILURE finding voting `DELIVERY_BLOCKAGE_PATTERN`, one LUBRICATION_PATH_
DEGRADATION_PATTERN finding voting `DEVELOPING_RESTRICTION_PATTERN`) — see final report.

## Quality-first behavior

Before hypothesis synthesis, `_quality_gate_verdict` checks instrumentation coverage:

- zero registered sensors anywhere under the machine → `INSUFFICIENT_EVIDENCE` (nothing has
  even been checked)
- ≥50% (configurable, `quality_gate.unusable_fraction_threshold`) of sensors with a real
  `SensorQualityState` row reporting `UNUSABLE` → `SENSOR_OR_DATA_QUALITY_LIMITATION`,
  overriding whatever the rule/ML/state evidence would otherwise have said

`registered_sensor_count` is read from the asset hierarchy (`FeatureSourceRepository.
registered_sensors`), not from how many sensors already have a `SensorQualityState` row — a
sensor that is commissioned but has never reported yet is still real instrumentation, not
zero coverage (a real bug found and fixed this phase; see final report "Bugs found").

## "Checked but normal" vs. "nothing was checked"

`sources_checked = bool(rule_finding_ids or ml_result_ids or state_estimate_ids)`.
`INSUFFICIENT_EVIDENCE` is only returned when nothing was checked at all AND no source voted
`NORMAL_OPERATION`; a machine with real evidence that simply shows nothing abnormal correctly
returns `NORMAL_OPERATION` at `HIGH` confidence instead (a second real bug found and fixed
this phase — a Kalman-stable machine was previously misreported as insufficient evidence).

## Condition lifecycle

Five states (`app.domain.enums.ConditionLifecycle`): `DETECTED` (default, first observation
or the type/severity changed), `DEVELOPING` (same condition type persists for
`developing_after_consecutive` — default 2 — recent assessments), `PERSISTENT` (persists for
`persistent_after_consecutive` — default 3), `IMPROVING` (severity dropped from the prior
assessment while the type is unchanged), `RESOLVED` (current assessment is `NORMAL_OPERATION`
immediately following a non-normal one). `first_detected_at` is inherited across consecutive
same-type assessments (`classify_lifecycle` returns `inherit_first_detected_at`), pure logic
in `services/lifecycle.py`, no I/O.

## Explainability contract

Every `ConditionAssessment.evidence_summary` carries: `what_is_happening` (one sentence),
`why` (per-source rationale strings), `supporting_evidence` / `contradicting_evidence`,
`data_trustworthiness` (`TRUSTED`/`CAUTION`/`NO_TRUSTED_DATA`), and `unknowns` (explicit gaps,
e.g. "No ML inference results are available for this machine."). `limitations` and
`recommended_next_evidence` are separate top-level fields consumed directly by Phase 14.

## API

- `GET /api/v1/conditions/machines/{id}/latest` — computes and persists a fresh assessment
- `GET /api/v1/conditions/machines/{id}/history` — read-only, `start`/`end`/`limit`
- `GET /api/v1/conditions/metrics` — unscoped Prometheus-text counters (no periodic worker
  exists for this package, same precedent as Phase 12 ADR-109)

## Persistence

`ConditionAssessment` (migration `13d670ebdb0c`) is append-only per machine — every call to
`/latest` inserts a new row rather than updating in place, so `history` is a true audit trail.
`ConditionAssessmentRepository.insert()` calls `session.refresh()` after flush so the returned
row's enum-typed columns are real `Enum` instances, not raw strings (a real SQLAlchemy pitfall
found and fixed this phase; see final report).

## Known limitations

Machine-level granularity only (`component_id` always `null`, matching Phase 10-12's
machine-scoped feature/state vectors). Confidence is a categorical heuristic derived from
evidence-source count and strength tier, not a calibrated statistical model. Evidence-hierarchy
weights (`rule_finding_map`, `ml_classification_map`, `default_severity`, `lifecycle`
thresholds) live in versioned YAML config and are demo-scale defaults, not validated
industrial thresholds.
