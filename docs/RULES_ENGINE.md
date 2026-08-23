# Rules Engine — Phase 9 Design & Implementation

Status: COMPLETE (Phase 9). See `IMPLEMENTATION_STATUS.md` for the verification record and
`TECHNICAL_DECISIONS.md` (ADR-077–ADR-083) for the architectural decisions.

## 1. Purpose

The rules engine produces **structured evidence findings**, not diagnoses. It answers:

> "Given current telemetry, quality, and baselines, what deterministic evidence pattern
> matches?"

It never answers "what is wrong with this machine" — that is Phase 13 Condition
Intelligence's job, which this phase's `RuleFinding` rows feed as an input. Every finding
uses calibrated causal language (`docs/FAILURE_MODE_CATALOG.md` §13) and carries an explicit
`limitations` list of what it does NOT prove.

## 2. Edge vs. central distinction

`edge.rules.engine.LocalRuleEngine` (Phase 5) is a **different, smaller system**: exactly
four generic checks (out-of-range, reservoir critical, pump-running-without-delivery,
sensor-fault), no baseline awareness, no cross-signal patterns, runs with zero cloud
dependency for basic asset/technician protection. This phase's `RuleEngine` is central,
baseline-aware, versioned, and produces the richer 17-type evidence taxonomy — it never
duplicates or replaces the edge layer, which keeps operating unchanged.

## 3. Architecture

```
backend/app/rules_engine/
  domain/      pure, DB-free data + math: context (SignalEvaluation/ReservoirSignal
               Evaluation/CycleSignalEvaluation/MachineRuleContext), deviation (MAD-distance
               classification for non-STANDARD baselines), strength (evidence-strength
               combination), results (RuleFindingCandidate)
  rules/       pure check_* functions per finding type, one module per family:
               single_signal, cycle, cross_signal, bearing, quality
  services/    orchestration: RuleEngine (context building + rule dispatch + lifecycle
               application), lifecycle (the debounce/hysteresis state machine),
               query_service
  repositories/ RuleFindingRepository — the only writer of `rule_finding`
  workers/     worker.py (periodic live evaluation), reprocess.py (historical CLI)
  config/      RulesPolicy (pydantic) + demo_rules_policy.yaml
```

Mirrors `app.baselines`'/`app.data_quality`'s module shape deliberately — same
architectural family. `RuleEngine.evaluate_machine` is the single orchestrator both the live
worker and the reprocess CLI call, mirroring `BaselineEngine`'s "one method, two callers."

## 4. Inputs (brief §3, mandatory)

Only Phase 6 `telemetry`, Phase 7 `sensor_quality_state`, and Phase 8 `BaselineProfile`
(ACTIVE only). Never the simulator's ground truth — structurally impossible, since
`RuleEngine` never imports anything from `simulator.engine.output`/`GroundTruthRecord`, only
`app.repositories.telemetry`/`app.data_quality.repositories.*`/`app.baselines.repositories.*`.

## 5. Quality gating (brief §4)

Per-signal: only `Telemetry.quality == GOOD` rows from a sensor whose
`SensorQualityState.eligibility != INELIGIBLE` are used. `ELIGIBLE_WITH_CAUTION` samples are
included but cap the resulting `evidence_strength` at `MODERATE`
(`RulesPolicy.quality.caution_caps_evidence_strength_at`), never silently excluded.

Machine-level: if fewer than `minimum_eligible_sensor_fraction` (default 50%) of a machine's
currently-tracked sensors are eligible, **no equipment-condition finding evaluates at all**
this cycle — only `INSUFFICIENT_TRUSTED_DATA` (`app.rules_engine.rules.quality`) may fire,
enforced in `RuleEngine._evaluate_all_rules`'s very first check, which short-circuits before
any other rule runs (brief §40/§41, mandatory — verified live via
`scripts/verify_rules.sh` and `test_insufficient_trusted_data_suppresses_equipment_findings`).

## 6. Baseline awareness (brief §5, §43 mandatory)

For `STANDARD`-metric-kind baselines (PRESSURE, FLOW, PUMP_CURRENT, PUMP_RUNTIME,
BEARING_TEMPERATURE, VIBRATION_RMS/PEAK, RPM, LOAD), `RuleEngine` reuses Phase 8's own
`app.baselines.services.deviation_service.evaluate` directly — which resolves through the
fallback hierarchy (contextual → operating-state → sensor-level → engineering reference) and
only ever queries `state == ACTIVE` rows (`BaselineProfileRepository.get_active`). A STALE,
CANDIDATE, BUILDING, or INSUFFICIENT_DATA baseline is therefore structurally never consulted
— not by a rules-layer filter, but because Phase 8's own resolution query never returns one.
For `RESERVOIR_TREND`/`CYCLE_METRIC` kinds (which `deviation_service` doesn't cover),
`RuleEngine` queries `BaselineProfileRepository.list_current_for_machine` and filters to
`state == ACTIVE` itself before use — same guarantee, applied explicitly. Verified directly:
`test_only_active_baseline_consumed_not_stale`.

Engineering limits (`STATIC_ENGINEERING_REFERENCE`) and learned baselines remain the two
separate lineages Phase 8 already keeps apart — the rules engine doesn't introduce a third
distinction, it just consumes whichever the fallback hierarchy resolves to.

## 7. Rule taxonomy (brief §9/§10)

| Category | Finding types |
|---|---|
| HYDRAULIC | `FLOW_BELOW_CONTEXTUAL_BASELINE`, `PRESSURE_ABOVE_CONTEXTUAL_BASELINE` |
| PUMP | `PUMP_CURRENT_ABOVE_BASELINE`, `PUMP_RUNTIME_ABOVE_BASELINE` |
| RESERVOIR | `RESERVOIR_LEVEL_LOW`, `RESERVOIR_DEPLETION_ABNORMAL` |
| LUBRICATION_CYCLE | `PRESSURE_BUILD_SLOW`, `CYCLE_DURATION_ABOVE_BASELINE`, `CYCLE_COMPLETION_FAILURE` |
| BEARING_CONDITION | `BEARING_TEMPERATURE_ABOVE_CONTEXTUAL_BASELINE`, `VIBRATION_ABOVE_CONTEXTUAL_BASELINE`, `INDEPENDENT_BEARING_CONDITION_PATTERN` |
| CROSS_SIGNAL | `FLOW_PRESSURE_RESTRICTION_PATTERN`, `FLOW_PRESSURE_LEAKAGE_PATTERN`, `PUMP_DEGRADATION_PATTERN`, `LUBRICATION_PATH_DEGRADATION_PATTERN` |
| SENSOR_QUALITY_DEPENDENT | `INSUFFICIENT_TRUSTED_DATA` |

Exactly the 17 catalog entries brief §10 requires — `app.domain.enums.RuleFindingType`.

## 8. Single-signal rules (brief §11)

Each is *directional*: `PRESSURE_ABOVE_CONTEXTUAL_BASELINE` fires only when the deviation
is both material (Phase 8's `MILD_DEVIATION`/`STRONG_DEVIATION`, never
`WITHIN_EXPECTED_RANGE`) **and** the observed value sits above the baseline median — a
strong deviation in the opposite direction is a different (or no) finding, not this one
(`app.rules_engine.rules.single_signal._directional_finding`). `RESERVOIR_LEVEL_LOW` is
engineering-limit-based, not baseline-based (a reservoir is "low" relative to a configured
physical minimum, matching `docs/FAILURE_MODE_CATALOG.md` §7, not its own learned history).

## 9. Cross-signal rules (brief §12-§15)

`app.rules_engine.rules.cross_signal` — each pattern is a `requires`/`supporting`/`excludes`
combination over the single-signal/cycle findings that already fired *this same cycle*
(`RulesPolicy.cross_signal`, config-driven, not hardcoded):

- **Restriction**: requires `FLOW_BELOW` + `PRESSURE_ABOVE`; supporting `PUMP_CURRENT_ABOVE`/
  `PUMP_RUNTIME_ABOVE` escalate confidence one level.
- **Leakage**: requires `FLOW_BELOW` + `RESERVOIR_DEPLETION_ABNORMAL`; **excludes**
  `PRESSURE_ABOVE` — the defining distinction from restriction (`docs/FAILURE_MODE_CATALOG.md`
  §5's flat-or-falling pressure signature vs. restriction's rising one).
- **Pump degradation**: requires `PRESSURE_BUILD_SLOW`; **excludes** `PRESSURE_ABOVE` — slow
  rise time without an elevated peak, the opposite signature from restriction.
- **Lubrication path degradation** (generic catch-all): fires only when no more specific
  pattern matched this cycle, and ≥2 distinct lubrication-system signals are deviating —
  exactly the "evidence exists but doesn't cleanly separate" case brief §15 asks for.

Verified live end to end (`scripts/verify_rules.sh` step 7): on the real flagship topology,
which has no `FLOW` sensor, the generic `LUBRICATION_PATH_DEGRADATION_PATTERN` correctly
fires from `PRESSURE_ABOVE` + `PUMP_CURRENT_ABOVE`, while `FLOW_PRESSURE_RESTRICTION_PATTERN`
correctly never fires — proving the exclusion/requirement logic behaves honestly under real
missing-instrumentation conditions, not just in a controlled test topology.

## 10. Bearing-condition rules (brief §16-§17, §39 mandatory)

`INDEPENDENT_BEARING_CONDITION_PATTERN` (`app.rules_engine.rules.bearing`) fires per bearing
only when a temperature and/or vibration finding is present **and** every
lubrication-system-signal finding type (`RulesPolicy.bearing.lubrication_signal_types`) is
currently absent machine-wide — the mandatory differentiation from a lubrication-caused
bearing consequence (`docs/FAILURE_MODE_CATALOG.md` §12). Verified:
`test_independent_bearing_pattern_suppressed_when_lubrication_abnormal`.

## 11. Temporal sequencing (brief §18)

Every `RuleFinding` carries `first_detected_at`/`last_detected_at`, derived purely from this
engine's own persisted finding history — never simulator ground truth. A future consumer
(Phase 13) can compare a lubrication-path finding's `first_detected_at` against a
bearing-condition finding's own `first_detected_at` for the same machine to observe lead
time, exactly the "lubrication deviations emerge first, bearing consequences later" pattern
Phase 4's reference dataset demonstrates physically — this phase records the timestamps that
make that comparison possible without computing the comparison itself (out of scope, per
brief §51).

## 12. Windowed rules (brief §19)

Sensor-type-aware, not one global window (`RulesPolicy.window_minutes_for`): 30min default,
60min for `LUBRICATION_CYCLE`/`BEARING_CONDITION`, 6h for `RESERVOIR` (a depletion trend
needs a longer horizon than a point check).

## 13. Debounce and hysteresis (brief §20, mandatory)

`app.rules_engine.services.lifecycle.decide` — a pure state machine (unit-tested in
isolation, mirroring `app.baselines.services.promotion`'s testing convention):

- **Onset**: `CANDIDATE → ACTIVE` requires a rule to fire on `required_stable_cycles`
  *consecutive* worker cycles (default 3, config-overridable per finding type — e.g.
  `RESERVOIR_LEVEL_LOW`/`CYCLE_COMPLETION_FAILURE` use 2, a threshold crossing needing less
  confirmation than a noisy deviation). A consecutive-cycle counter, not an exact N-of-M
  sliding window — the same simplification Phase 8's own stability gate documents.
- **Recovery**: `ACTIVE → RECOVERING → RESOLVED` requires two consecutive clean (non-firing)
  cycles, identical to Phase 7's `QualityIssue` window-scoped lifecycle — avoids flapping on
  one borderline cycle.
- A `CANDIDATE` that stops firing before ever reaching `ACTIVE` resolves **directly** —
  nothing to "recover" from, since it never became a confirmed finding.

Verified live: `scripts/verify_rules.sh` steps 5-6 (three reprocess cycles reach `ACTIVE`);
`test_finding_recovers_and_resolves_when_condition_clears` (full ACTIVE→RECOVERING→RESOLVED
cycle against live Postgres).

## 14. Evidence strength (brief §8)

`EvidenceStrength`: `LOW`/`MODERATE`/`STRONG` — explicitly not an ML probability, never a
fabricated percentage. Derived from Phase 8's own deviation classification
(`MILD_DEVIATION → MODERATE`, `STRONG_DEVIATION → STRONG`), capped at `MODERATE` for
`ELIGIBLE_WITH_CAUTION` evidence (§5 above), and escalated by one level when a cross-signal
pattern has independent corroborating evidence (§9).

## 15. Severity and criticality (brief §23-§24, mandatory separation)

`app.rules_engine.services.rule_engine._severity_for`: base severity comes entirely from
`evidence_strength` (`RulesPolicy.severity.base_by_evidence_strength` —
`LOW→INFO`/`MODERATE→WARNING`/`STRONG→HIGH`). Criticality (`Machine.criticality`/
`Bearing.criticality`, Phase 2) may escalate that severity by exactly one level when both the
component is `HIGH`/`CRITICAL` criticality **and** the evidence is already `STRONG` — it
never lowers evidence strength, never fabricates a finding, and never runs before a finding
already exists. This is the structural enforcement of "criticality affects priority, never
whether evidence exists" (brief §24).

## 16. Structured evidence (brief §25)

Every `RuleFinding.evidence` is a nested dict keyed by signal name (e.g.
`{"pressure": {"observed": ..., "baseline_median": ..., "standardized_distance": ...}}`),
never a single opaque message string. `message` is a short, calibrated-language label for
the same evidence, not the sole output.

## 17. Causal language (brief §26)

Every finding's `message` uses "is materially above/below...", "pattern is consistent
with...", "further inspection recommended" — never "confirmed" language
(`docs/FAILURE_MODE_CATALOG.md` §13's rules, applied identically here). Every finding
carries a non-empty `limitations` list stating what it does NOT prove — enforced by
convention across every `check_*` function (verified spot-check:
`test_restriction_pattern_fires_end_to_end` asserts `limitations` is never empty for a
cross-signal pattern).

## 18. Persistence (brief §27)

One table, `rule_finding` (migration `615a5631e98e`), denormalized for the identical reason
`BaselineProfile` (Phase 8, ADR-071) chose one table over three — structured
evidence/limitations/quality_context/baseline_version_ids/source_event_ids as JSONB on the
same row as lifecycle/severity/version metadata, since a finding is always read and written
as one unit. Partial unique index `uq_rule_finding_active_scope` on
`(tenant_id, machine_id, component_id, rule_id, rule_version)` where
`state IN ('CANDIDATE', 'ACTIVE', 'RECOVERING')` enforces at most one non-terminal row per
lineage — `RESOLVED` rows are never deleted or overwritten, a later recurrence opens a fresh
row.

## 19. Idempotency (brief §28)

Re-evaluating the same window twice in a row for a still-firing finding always resolves to
`REFRESH_ACTIVE` (update in place) or `ADVANCE_CANDIDATE`, never a duplicate insert — the
partial unique index makes a second `CREATE_CANDIDATE` for the same lineage structurally
impossible even if application logic ever raced. Verified live
(`scripts/verify_rules.sh` step 10: a fourth identical reprocess leaves exactly one
non-terminal row) and in `test_idempotent_reevaluation_does_not_duplicate_active_finding`.

## 20. Worker (brief §30, §46-§47)

`python -m app.rules_engine.workers.worker` — a periodic `asyncio` loop
(`RULES_WORKER_CYCLE_SECONDS`, default 300s), **not** a Kafka consumer, for the identical
reason Phase 8's baseline worker isn't one: a finding is a judgment over a window of
evidence, not a single-event decision, and rules already depend on Phase 8 baselines that
are themselves only periodically refreshed — reacting to every raw telemetry event would
race ahead of the baselines the rules need (ADR-078). Discovers tracked machines from Phase
7's `sensor_quality_state` (mirroring `app.baselines.workers.worker`'s own discovery
pattern), per-machine `SAVEPOINT` isolation, and — new relative to Phase 7/8's precedent —
**per-candidate `SAVEPOINT` isolation inside `_apply_lifecycle` too** (ADR-079): a real bug
found during live verification (a pathological `float("inf")` distance value, invalid JSON,
crashing mid-transaction) demonstrated that one bad finding could otherwise roll back every
other valid finding computed for the same machine in the same cycle. Own health/metrics on
port 8085 via the shared `app.observability.worker_health` server.

## 21. Reprocessing (brief §31)

```
python -m app.rules_engine.workers.reprocess \
  --tenant-id <uuid> [--machine-id <uuid>] --start <iso8601> --end <iso8601>
```

Calls the exact same `RuleEngine.evaluate_machine` method as the live worker, with
`window_override=(start, end)`. Never deletes prior findings — participates in the same
CANDIDATE/ACTIVE/RECOVERING/RESOLVED lifecycle as a live cycle. Without `--machine-id`,
reprocesses every machine currently tracked for the tenant.

## 22. API (brief §32)

Tenant-scoped via `get_current_tenant`: `GET /api/v1/rules/findings` (filterable by
`machine_id`/`finding_type`/`severity`/`state`/`rule_id`/`start`/`end`),
`GET /api/v1/rules/machines/{machine_id}`, `GET /api/v1/rules/findings/{finding_id}`,
`GET /api/v1/rules/summary`.

## 23. Frontend validation view (brief §34)

`/rules` — summary cards, a state/severity-filterable findings table, and a click-to-expand
detail panel showing message, limitations, rule/policy/category metadata, and the full
structured evidence JSON (satisfying brief §44's explainability requirement visually, not
just via the API). No AI diagnosis, no health score — a plain read of the API response
(ADR-008).

## 24. Verification scope

The flagship (Ore Transfer Conveyor CV-101)'s real registered sensor set — PRESSURE, PUMP_CURRENT,
RESERVOIR_LEVEL, RPM, BEARING_TEMPERATURE (×2), VIBRATION_RMS (×2) — has **no FLOW,
PUMP_RUNTIME, or CYCLE_COMPLETION sensor** in the Phase 2 demo seed topology.
`FLOW_PRESSURE_RESTRICTION_PATTERN`/`FLOW_PRESSURE_LEAKAGE_PATTERN` (which require a `FLOW`
signal by their own `requires` definition) therefore cannot be demonstrated against this
specific live demo topology — verified instead via `backend/tests/rules_engine/
test_rule_engine.py` against a full synthetic topology with real Postgres and the real
`RuleEngine` (not mocked). `scripts/verify_rules.sh` demonstrates every finding type the
real flagship sensors *do* support (`PRESSURE_ABOVE_CONTEXTUAL_BASELINE`,
`PUMP_CURRENT_ABOVE_BASELINE`, `RESERVOIR_LEVEL_LOW`, `RESERVOIR_DEPLETION_ABNORMAL`,
`LUBRICATION_PATH_DEGRADATION_PATTERN`, `INSUFFICIENT_TRUSTED_DATA`) plus the correct
*absence* of the restriction pattern given missing FLOW instrumentation.
`edge/scripts/run_rules_validation.py` additionally proves the full real chain (simulator →
edge → MQTT → Kafka → TimescaleDB → baselines → rules) delivers and evaluates real
gradual-restriction scenario physics without error.

## 25. Known limitations

- Load/RPM/context resolution for single-signal rules inherits Phase 8's own simplification
  (operating-state-based, no independent continuous load/RPM buckets — see
  `docs/BASELINES.md` §27).
- Cross-signal pattern matching uses "did finding_type X fire anywhere on this machine this
  cycle" (first-occurrence-per-type) rather than per-component pairing — at this reference
  implementation's scale (1-2 circuits per machine), a reasonable simplification, but a
  fleet with many circuits per machine sharing one pump would want per-circuit pattern
  matching instead.
- `PRESSURE_BUILD_SLOW`'s rise-time comparison is a plain ratio against baseline, not a
  robust standardized distance — no rise-time MAD is tracked by Phase 8's `CYCLE_METRIC`
  baseline (only a duration MAD).
- The reprocess CLI and live worker read a sensor's *current* quality eligibility, not
  historical point-in-time eligibility — the same disclosed limitation Phase 7/8's own
  reprocessing tools carry forward (ADR-070).
- No sub-minute-latency evaluation — bounded by `RULES_WORKER_CYCLE_SECONDS` (default 300s),
  matching Phase 8's baseline worker's own latency ceiling this phase's rules already inherit.
