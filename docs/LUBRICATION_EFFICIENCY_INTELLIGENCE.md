# Lubrication Efficiency Intelligence — Domain & Architecture Design

**Status: Pass 1 implemented (Machine Power → Contextual Expected Power → Energy
Residual → Data-Quality-Gated Energy Assessment).** This is a capability extension after
the completed roadmap (Phases 1–37+) — not a new numbered phase, and not a commitment
that every remaining section here ships exactly as designed.

**Implemented** (§3–§9, §14 slice): `SensorType.MACHINE_POWER`; real power telemetry for
the curated hosted-demo fleet's representative machines (`backend/scripts/seed_*.py` —
the curated demo fleet's actual telemetry source, confirmed independent of the
`simulator` package at runtime) plus a machine-driveline power physics extension in
`simulator/simulator/physics/` (design §12) for that package's own separate scenario
-runner use; expected-power resolution reusing `app.baselines`'
`CONTEXTUAL_ASSET_BASELINE` unchanged (§4); `energy_residual_kw`/`energy_residual_pct`
(§5, with the documented invalid-denominator guard); the persisted `EnergyAssessment`
model/repository/service/API (§7, §14 minus `lubrication_attribution`); data-quality
gating (§7); an observable-only `ENERGY_RESIDUAL` evidence function
(`app.energy.domain.evidence`, §8/§13) that is **not** wired into
`ConditionEngine`/`synthesize()` yet. See ADR-176 and the implementation report for exact
files, tests, and verification.

**Not yet implemented** (deliberately deferred, per this pass's own scope): lubrication
attribution (§6), Condition/Decision Intelligence wiring (§8), maintenance verification
(§9), carbon estimation (§10–§11), the ML regression opportunity (§13, still assessed as
not justified for now), and all frontend UX (§16). The rest of this document describes
the full intended design; only the slice above is real today.

## Product definition

**Lubrication Efficiency Intelligence estimates whether an asset's energy demand is materially
different from its expected demand under comparable operating conditions, and evaluates
whether lubrication-condition evidence plausibly contributes to that deviation.**

The central product question this answers:

> Is deteriorating lubrication causing this asset to consume more energy than expected under
> comparable operating conditions, and did the energy behavior improve after intervention?

This is deliberately **not**:

- a generic sustainability dashboard bolted onto the product
- a CO2e calculator applied to arbitrary energy numbers
- a claim that "all excess energy is caused by lubrication"
- a claim of causality from motor/pump current alone
- a claim of field-validated savings

The system keeps two things structurally separate, always:

**A. Observed energy deviation** — a measured fact: actual power draw differs from the
power this asset was expected to draw under comparable operating conditions. This is
computable from telemetry alone and carries no claim about *why*.

**B. Lubrication-attribution confidence** — a separate judgment: how strongly the *other*
evidence this platform already collects (rule findings, state estimates, ML evidence, data
quality) supports lubrication condition as a plausible contributor to that deviation. This
follows the exact same evidentiary discipline `docs/CONDITION_INTELLIGENCE.md` already
enforces for physical conditions — evidence, tiers of strength, explicit uncertainty, never an
invented causal percentage.

Worked example, in the product's own voice:

```
Energy deviation:      +6.2% above contextual expectation
Lubrication attribution: MODERATE
Reason:
  - lubrication delivery deteriorating (rule finding: PRESSURE_ABOVE_CONTEXTUAL_BASELINE)
  - bearing temperature elevated (rule finding, corroborating)
  - vibration elevated (corroborating)
  - process load comparable to the baseline population (data trust: acceptable)
```

Never:

```
"82% of this energy loss is caused by lubrication."
```

...unless a genuinely validated causal-attribution model exists, which it does not today and
is not proposed here (§13).

## What already exists — reuse, do not duplicate

An architecture inventory pass (read-only, no files modified) confirmed the following. Every
piece of this design below builds on one of these, never a parallel mechanism.

| Need | Existing mechanism | Reuse verdict |
|---|---|---|
| "Expected value under comparable operating conditions" | `app.baselines` — `CONTEXTUAL_ASSET_BASELINE` strategy (`app/baselines/strategies/contextual.py`), bucketed by `(operating_state, cycle_phase)`, robust median/MAD statistics, documented fallback to `ROLLING_ASSET_BASELINE` | **Reuse directly.** This *is* an expected-energy model already, for a new measurement type. |
| Declaring/computing a new signal's derived features | `app.features` — `definitions/catalog.py` feature-set declarations, `services/feature_engine.py` computation, existing `feature_set`/`feature_set_version` provenance fields already on `FeatureVector`/`MLInferenceResult` | **Reuse directly.** A new feature set follows the existing catalog pattern. |
| A slowly-drifting, Kalman-filtered latent condition | `app.state_estimation` — `StateEstimator`, two declared states (`LUBRICATION_DELIVERY_STATE`, `BEARING_CONDITION_STATE`, `state_estimation_v1.yaml`) | **Do not reuse.** An energy residual is a per-tick comparison against a contextual expectation, not a physically slowly-drifting latent quantity to be Kalman-filtered. Forcing it into `StateEstimator` would be architecturally dishonest for no benefit — see §4. |
| A new evidence source feeding condition synthesis | `app.condition_intelligence` — `EvidenceItem(source_type, source_id, strength, condition_hint, description, severity)`; `source_type` is already a plain string (`"RULE_FINDING"`, `"ML_RESULT"`, `"STATE_ESTIMATE"`), not a closed enum | **Reuse directly, zero schema change.** A new `source_type="ENERGY_RESIDUAL"` value follows the exact pattern `_evidence_from_rule_finding`/`_evidence_from_ml_result`/`_evidence_from_state_estimate` already use. |
| "A secondary factor may raise urgency but never manufacture a diagnosis on its own" | `app.decision_intelligence` — `DecisionEngine`'s own documented rule that criticality "may shift priority up or down; it can never manufacture a fault-pattern decision" from a non-fault condition (`decision_synthesis._NON_FAULT_TYPES`) | **Direct precedent, reuse the same pattern** for energy-urgency (§8). |
| Data-quality gating before any assessment is trusted | `app.data_quality` — per-sensor `QualityState` (`TRUSTED`/`USABLE_WITH_CAUTION`/`UNUSABLE`), and the aggregate machine-level rollup pattern `ConditionEngine._overall_quality_state` already uses (`TRUSTED`/`CAUTION`/`NO_TRUSTED_DATA`) | **Reuse directly**, at both grains (§7). |
| Model registry / lifecycle governance for any future ML component | `app.ml` + `ml_service` — `EXPERIMENT→VALIDATED→STAGING→PRODUCTION`, `MLInferenceResult`, `MLInferenceOrchestrationService` | **Reuse directly if/when an ML model is ever justified** (§13) — no redesign needed, only new enum members. |
| Labeling an estimate honestly as demo/estimated, never validated | `app.product_metrics` — North Star metric explicitly labeled `DEMO_ESTIMATE`/`MEASURED_PLATFORM_METRIC` (`docs/PRODUCT_METRICS.md`), computed live from real rows, never hand-set | **Reuse the same labeling discipline** for every CO2e number this capability ever shows (§10–§11). |
| A per-tenant/per-site configurable numeric factor with provenance | *(none — genuinely new)* | **New, small surface area required.** The only existing "configurable per deployment" precedent is versioned global YAML policy (`condition_intelligence_v1.yaml`'s `policy_version`), not a per-tenant/per-site DB-backed value. An electricity emission factor that varies by site/grid region needs a new, minimal config table — see §10. This is the one piece of this design that is not simply "reuse an existing pattern." |

## Data gaps

Two real gaps, both scoped in this design:

1. **No electrical power (kW), energy (kWh), voltage, torque, or power-factor concept
   anywhere in the domain model, telemetry envelope, or simulator.** `SensorType` (`app/
   domain/enums.py`) has no such member. `PUMP_CURRENT` exists but is a real, physically
   distinct signal — the *lubrication pump's own small motor current*, driven in the
   simulator (`simulator/simulator/physics/pump.py`/`circuit.py`) purely by pump discharge
   pressure. It is not, and must never be treated as, a proxy for the *machine's own
   driveline power* (§3).
2. **No per-tenant/per-site configurable factor with provenance exists today.** An emission
   factor needs one (§10).

Everything else this capability needs — contextual expectation modeling, evidence fusion,
decision integration, data-quality gating, lifecycle-governed ML, honest-labeling discipline —
already exists and is reused, not reinvented.

## 3. Energy signal model

### New signal, not an abuse of an existing one

A new `SensorType` member is required: **`POWER`** (instantaneous electrical power, kW,
delivered at the machine's own drive/motor — the thing the failure modes in
`docs/FAILURE_MODE_CATALOG.md` (restriction, bearing degradation, pump degradation) would
actually be expected to load). This is deliberately **not** `PUMP_CURRENT`: `PUMP_CURRENT` is
real, already-modeled, and stays exactly what it is today (a lubrication-pump-motor signal
feeding `check_pump_current_above_baseline` and baseline/feature computation) — conflating it
with machine driveline power would misrepresent both.

Current in amperes must never be presented as power or energy without an explicit,
labeled voltage/power-factor assumption. If a deployment only has current telemetry (no real
power meter), any power/energy figure derived from it must carry an explicit
`derivation: "estimated_from_current"` provenance flag distinct from a real power-meter
reading (`derivation: "measured"`) — never presented identically in the UI or evidence text.

### Signal set

| Concept | Representation | Source |
|---|---|---|
| Instantaneous power | `SensorType.POWER`, unit `kW`, real telemetry (meter) or explicitly-flagged current-derived estimate | New sensor type |
| Energy consumption | `energy_kwh` — trapezoidal integration of `POWER` telemetry over a window | Derived, computed in `app.features` (a rate-to-quantity integration is a normal feature-engineering operation, not a new subsystem) |
| Expected power | `expected_power_kw` — contextual-baseline output for `POWER`, bucketed the same way `CONTEXTUAL_ASSET_BASELINE` already buckets any other measurement | `app.baselines`, reused |
| Energy residual | `energy_residual_kw` / `energy_residual_pct` (§5) | Derived from the two above |
| Operating context | `operating_state`, `RPM`, `LOAD` — already real, already telemetered | Existing (`app.domain.enums.OperatingState`) |

## 4. Expected energy model

**Recommendation: extend the existing contextual baseline engine. Do not introduce a new ML
model for v1.**

`CONTEXTUAL_ASSET_BASELINE` already computes exactly "expected value under comparable
operating conditions" — bucketed by `(operating_state, cycle_phase)`, robust
median/MAD-style statistics, a documented fallback hierarchy when a context bucket is sparse.
Registering `POWER` as a new baselined measurement type gets `expected_power_kw` with:

- **no new statistical method** (reuses `compute_robust_statistics`)
- **no new provenance mechanism** (reuses `baseline_version_ids`, already surfaced on
  `RuleFinding`/`ConditionAssessment`)
- **no new confidence vocabulary** (reuses the baseline engine's own sample-sufficiency /
  fallback-tier signal)

This is "Option A/B" from the brief — a contextual statistical baseline — deliberately over a
regression or ML model, because:

- it needs no training data or labels, works from day one of telemetry, same as every other
  baseline today
- its provenance is already fully explainable (a version id + a bucket description), matching
  this product's "never an opaque number" discipline
- a regression model is a legitimate *future* improvement (§13), not a defensible *first*
  implementation — CLAUDE.md's own AI/ML boundary ("Do not use ML simply because AI sounds
  more advanced") applies directly here

**Known limitation to flag honestly, not hide**: `RUNNING_NORMAL_LOAD` today is a single
context bucket (`app/domain/enums.py`'s `OperatingState`). If actual load varies materially
*within* that one state (a real machine rarely runs at one exact load level continuously),
the expected-power baseline may be too coarse — a genuine v2 refinement (binning by a
continuous `LOAD` value, not just `operating_state`), explicitly deferred, not solved here.

### Output shape

```
expected_power_kw       # baseline center, this operating context
expected_lower_kw       # baseline robust lower bound
expected_upper_kw       # baseline robust upper bound
actual_power_kw         # current/window-averaged real telemetry
energy_residual_kw
energy_residual_pct
confidence              # baseline sample-sufficiency tier, existing vocabulary
baseline_version_ids    # provenance, existing field shape
```

## 5. Energy residual

```
energy_residual_kw  = actual_power_kw - expected_power_kw
energy_residual_pct = (actual_power_kw - expected_power_kw) / expected_power_kw
```

- **Positive residual**: the asset is consuming more power than expected under comparable
  conditions.
- **Negative or near-zero residual**: no current excess-energy evidence.

The residual is never called "lubrication loss" in code, API responses, or product copy. It is
an **energy deviation** — a measured fact — until the attribution layer (§6) evaluates whether
lubrication-condition evidence plausibly explains it. Naming discipline matters here the same
way it already matters in `docs/CONDITION_INTELLIGENCE.md` ("evidence is consistent with", per
CLAUDE.md's "Failure Modes" wording rules) — never asserted causality from a residual alone.

## 6. Lubrication attribution

A distinct confidence vocabulary from `EvidenceItem.strength` (STRONG/SUPPORTING/WEAK/
EXPERIMENTAL, which grades *condition* evidence), because attribution is a different
question — "does the evidence I already trust support lubrication as a plausible contributor
to *this specific energy deviation*", not "how strong is one evidence item toward a
condition":

```
NO_EVIDENCE   — no energy deviation observed, or no corroborating lubrication evidence exists
POSSIBLE      — energy deviation observed; at most weak/candidate corroborating evidence
MODERATE      — energy deviation observed; at least one non-experimental, non-weak
                lubrication-condition evidence item (rule finding, validated ML, or a
                trustworthy state estimate) points the same direction
STRONG        — energy deviation observed; multiple independent, non-experimental evidence
                sources corroborate (e.g. a STRONG rule vote AND a trustworthy deteriorating
                state estimate), same "independent corroboration" bar
                `synthesis._TALLIED_STRENGTHS`/HIGH-confidence already requires
```

Attribution confidence is **derived**, never independently asserted:
`lubrication_attribution = f(energy_residual_sign_and_magnitude, existing ConditionAssessment
evidence_summary for this machine)` — it reads the *same* `EvidenceItem`s condition synthesis
already gathered (rule findings, state estimates, non-experimental ML), it does not invent new
ones. A machine with `NORMAL_OPERATION` and no active findings can never reach `MODERATE`/
`STRONG` attribution regardless of how large the energy residual is — the residual alone
proves nothing about cause (§17, "a lower energy reading is not automatically better" cuts
both ways: a higher one is not automatically lubrication's fault either).

Exact percentages ("82% caused by lubrication") are never produced — no model in this
architecture (§13) claims that level of causal resolution, and none should be implied.

## 7. Data-quality gating

Reuses the exact existing two-grain pattern:

- **Per-sensor** (`app.data_quality.QualityState`): the `POWER` sensor (and `RPM`/`LOAD` for
  context) must be `TRUSTED` (or `USABLE_WITH_CAUTION` with reduced confidence) before any
  `actual_power_kw` is computed. `UNUSABLE` → no energy assessment at all for this window, the
  same way `ConditionEngine` already refuses to assess on zero trusted evidence.
- **Aggregate/assessment-level** (mirroring `_overall_quality_state`): an `EnergyAssessment`
  carries its own `data_quality_state` (`TRUSTED`/`CAUTION`/`NO_TRUSTED_DATA`), gating what the
  assessment is allowed to claim:

| Condition | Effect |
|---|---|
| Bad/missing power measurement | No reliable `actual_power_kw` → no energy residual, no CO2e claim at all |
| Missing RPM/load context | `expected_power_kw` confidence reduced (same as any sparse-context baseline fallback tier) — never silently ignored |
| Poor lubrication-signal quality (pressure/flow/bearing sensors unusable) | Energy deviation may still be observed and reported; `lubrication_attribution` is capped at `POSSIBLE` at most — the deviation is real, but nothing corroborates a lubrication cause |
| No trustworthy data anywhere in the window | No energy assessment persisted; certainly no CO2e claim (§10–§11) |

## 8. Condition / Decision Intelligence connection

**Energy Intelligence is never independent** — it plugs into the existing two-stage evidence
→ decision pipeline, never bypasses it:

- **Condition Intelligence**: a materially elevated `energy_residual_pct` with at least
  `MODERATE` lubrication attribution becomes one more `EvidenceItem(source_type=
  "ENERGY_RESIDUAL", strength=..., condition_hint=<same family the corroborated rule/state
  evidence already points to>, description=...)`. Its strength tier follows the same
  discipline as every other source: it can be `SUPPORTING` (corroborating an
  already-plausible hypothesis) or `WEAK`, but — critically — **energy evidence alone can
  never independently establish a condition** (no `condition_hint` is voted from energy
  evidence with no other corroborating source; it is architecturally incapable of reaching
  `STRONG`). This mirrors `DecisionEngine`'s own documented rule almost exactly, one layer
  earlier.
- **Decision Intelligence**: an energy penalty **modifies urgency**, it never itself
  triggers a lubrication diagnosis — following the exact precedent `decision_synthesis
  ._NON_FAULT_TYPES` already enforces for criticality (criticality "may shift priority up or
  down; it can never manufacture a fault-pattern decision" from a non-fault condition). A
  worked example in the product's own voice:

```
Condition:        Restricted lubricant delivery developing
Energy evidence:  Power demand 7% above contextual expectation
Attribution:      Moderate lubrication-related efficiency-loss evidence
Decision:         Inspect lubrication delivery
Urgency:          Raised — reliability deterioration and energy penalty coexist
```

If there is no diagnosed condition (`NORMAL_OPERATION`, or `INSUFFICIENT_EVIDENCE`), an
energy residual — however large — produces no decision. It can, at most, be surfaced as a
standalone "elevated energy demand, cause undetermined" observation, never phrased as a
lubrication finding.

## 9. Maintenance verification

A new, dedicated comparison service (no existing reusable mechanism — `seed_flagship_story
.py`'s own hand-rolled recovery-telemetry replay is scenario-seeding code, not a reusable
verification service):

```
pre-intervention window   →  MaintenanceCase.created_at (or its condition_assessment's
                              first_detected_at) minus a configured lookback
maintenance event          →  MaintenanceCase.completed_at (real, existing field)
post-intervention window   →  a configured lookahead after completed_at
```

Both windows are filtered to **comparable operating context** (same `operating_state`
population the baseline itself already buckets by) and **comparable data quality** (both
windows must independently satisfy §7's gate) before any comparison is computed — an
"improvement" measured while comparing a high-load pre-window to a low-load post-window is not
a real comparison, and the service must refuse to produce one rather than silently mislead.

```
pre_intervention_residual_kw
post_intervention_residual_kw
observed_residual_change_kw   = pre_intervention_residual_kw - post_intervention_residual_kw
estimated_avoided_energy_kwh  = observed_residual_change_kw * relevant_operating_hours
verification_confidence       # LOW/MODERATE/HIGH — driven by: window data quality,
                                 population size in each window, operating-context comparability
```

Labeled **"Observed energy recovery"** / **"Estimated avoided energy"** in all product copy —
never **"saved energy"** unless the comparability criteria above are genuinely satisfied for
that specific case, and even then the estimate carries its `verification_confidence` alongside
it, never presented as a bare number.

## 10. Carbon estimation & provenance

```
estimated_co2e_kg = estimated_avoided_energy_kwh * electricity_emission_factor_kg_co2e_per_kwh
```

The emission factor is genuinely new configuration surface (§"What already exists" table — no
precedent to extend). Proposed minimal new entity, sited at `Site` (the grid-region-relevant
level, not `Tenant` — a multi-site tenant can span grid regions) or `Plant` if the asset
hierarchy needs finer granularity than `Site` already provides for this:

```
SiteEmissionFactor
  tenant_id
  site_id
  factor_value_kg_co2e_per_kwh
  factor_unit                    # always "kg_co2e_per_kwh", explicit not implied
  factor_source                  # free text: e.g. "national grid average, published by <ref>"
  effective_date
  location_method                # e.g. "location-based" vs "market-based" (GHG Protocol terms)
  last_updated_at
  last_updated_by
```

No universal default factor is hardcoded anywhere. If a site has no configured factor, no
CO2e estimate is produced for that site — an energy-only assessment (§4–§5) is still shown,
CO2e simply does not appear, the same "insufficient evidence → no claim" discipline as every
other gate in this design.

## 11. Carbon accounting boundary

Product language, enforced consistently everywhere this capability surfaces a number:

**Use**: "Estimated CO2e impact", "Estimated avoided emissions", "Location-based energy-related
estimate".

**Never use** (without a genuinely separate, audited process backing it, which does not exist
in this architecture): "Verified corporate carbon saving", "Carbon credit", "Certified
reduction".

Every CO2e number carries this disclaimer, verbatim or materially equivalent, wherever it
appears in the product (mirrors the existing `DEMO_ESTIMATE`/`MEASURED_PLATFORM_METRIC`
labeling discipline in `docs/PRODUCT_METRICS.md`):

> CO2e estimates are derived from measured/estimated energy changes and the configured
> electricity emission factor. They are operational estimates and are not audited corporate
> carbon accounting.

## 12. Simulator extension design (design only — not implemented this pass)

The simulator already has a real, physically coherent chain: `circuit.py`'s
`resistance_ratio` (driven by `restriction_factor`) raises `required_pressure_bar`, which
`pump.py`'s `motor_current_a = current_running_base_a + current_pressure_gain_a_per_bar *
pump.pressure_bar` genuinely turns into higher pump-motor current. That chain stays exactly as
it is — it is the *lubrication pump's own* energy story, real and already correct, and this
capability doesn't need to touch it.

What's missing is the **machine driveline power** signal, and its target formula should follow
`bearing.py`'s already-precedented pattern (baseline + load-gain term + a degradation/friction
-gain term keyed off real state variables the simulator already tracks — `bearing.health`,
`lubrication_effectiveness`):

| Scenario | Intended physical behavior |
|---|---|
| Healthy | `power_kw ≈ f(load_percent)` — a normal, load-driven baseline curve, no friction term |
| Lubrication restriction / rising friction | `power_kw` gradually rises under **comparable load** as `(1 - lubrication_effectiveness)` increases — same mechanism `bearing.py` already uses for temperature/vibration targets, applied to a new power target |
| Bearing deterioration | `power_kw` **and** temperature/vibration rise together — coherent with a shared `(1 - bearing.health)` term, never power alone |
| Recovery after lubrication maintenance | `power_kw` residual returns toward the expected curve as the same state variables recover — mirrors the existing recovery-telemetry pattern in `seed_flagship_story.py`/`seed_recovering_asset.py`, just for a new signal |
| Low reservoir | Must **not** automatically raise `power_kw` unless it genuinely reduces delivery/increases friction in the physics model first — reservoir level alone is not a friction mechanism; only cascade to a power effect if the existing delivery-degradation chain (`circuit.py`) actually reaches the bearing |
| Sensor/data-quality problem | Must **never** synthesize a fake physical energy change — a `POWER` sensor fault should behave exactly like any other sensor fault in the simulator (bad readings, not bad physics) |
| Commissioning (new/unbaselined machine) | Insufficient baseline history → `expected_power_kw` confidence is low/absent, same as any other newly-commissioned baseline today — not a simulator concern, a baseline-engine concern already handled |

Implementing this is out of scope for this pass — this table is the spec for whoever
implements it next.

## 13. ML regression opportunity — assessed, not recommended for v1

**Recommendation: do not build this yet.** The contextual baseline (§4) is the correct first
implementation; a regression model is a legitimate, well-scoped *future* enhancement once real
operating data (not synthetic) shows the baseline's context granularity is insufficient.

If/when it is justified:

- **Problem**: `EXPECTED_ENERGY_REGRESSION` — inputs = operating context (`operating_state`,
  `RPM`, `LOAD`, machine/asset-type), target = healthy expected power. `residual = actual -
  predicted`, same shape as §5.
- **Minimal registry extension** (confirmed via inventory — no redesign needed): one new
  `MLResultKind.REGRESSION` member (`app/domain/enums.py`, currently only `ANOMALY`/
  `CLASSIFICATION`), one new `ModelType` in `ml_service.domain.model_metadata` (currently only
  the anomaly/two-classifier types), and two new response fields (`predicted_value`,
  `prediction_interval_lower/upper`) parallel to the existing `anomaly_score`/`predicted_class`
  fields on `MLInferenceResult` — the lifecycle/registry/inference-orchestration machinery
  itself needs no change.
- **Training-data requirement**: needs many more *healthy, varied-context* observations than
  the fault classifiers do (a regression target needs density across the whole operating
  envelope, not just labeled fault windows) — the current 434-sample synthetic dataset that
  trains today's two classifiers is very unlikely to be sufficient breadth for this without a
  dedicated, much larger synthetic generation run (§12) or real field data.
- **Explainability**: reuse the existing per-inference feature-ablation pattern
  (`ml_service.explainability.explain`, already used for the classifier) — feature-ablation
  translates directly to a regression target.
- **Train/serve parity**: must reuse the exact same `Preprocessor` persisted-with-model
  pattern the classifiers already use correctly (confirmed no mismatch exists there today) —
  the SENSOR_FAULT domain-shift problem already documented for the existing classifiers
  (`condition_engine.py`'s own comment, and the ML governance pass's findings) is a direct
  warning: an energy regression model trained only on `ml-service`'s internal scenario
  simulator and served against `backend`'s independently-generated telemetry would risk the
  exact same distribution-shift failure mode, likely worse for a continuous regression target
  than a discrete classifier.
- **Field-data requirement**: per CLAUDE.md's Industrial Adoption Boundary, this must not be
  presented as production-ready without real machine histories — likely more true for a
  regression target (continuous, harder to sanity-check by eye) than for the existing
  classifiers.

## 14. Product output objects

Reusing existing field shapes/provenance conventions wherever an analog already exists
(`ConditionAssessment`'s `evidence_summary`/`quality_context`/`policy_version`/`engine_version`
pattern, `MLInferenceResult`'s `model_id`/`model_version` pattern):

```
EnergyAssessment
  tenant_id, machine_id, component_id
  as_of_timestamp
  actual_power_kw
  expected_power_kw, expected_lower_kw, expected_upper_kw
  residual_kw, residual_pct
  confidence                    # baseline sample-sufficiency tier
  data_quality_state            # TRUSTED / CAUTION / NO_TRUSTED_DATA
  lubrication_attribution       # NO_EVIDENCE / POSSIBLE / MODERATE / STRONG
  attribution_evidence          # the real EvidenceItem descriptions it was derived from
  baseline_version_ids          # provenance, same shape as existing baseline_versions
  engine_version, policy_version

EnergyOutcomeVerification
  tenant_id, machine_id, maintenance_case_id
  pre_window, post_window       # start/end timestamps, each with their own data_quality_state
  pre_intervention_residual_kw, post_intervention_residual_kw
  observed_residual_change_kw
  estimated_avoided_energy_kwh
  verification_confidence       # LOW / MODERATE / HIGH
  comparability_notes           # why (or why not) the two windows were judged comparable

CarbonEstimate
  tenant_id, site_id
  energy_outcome_verification_id  # or a standalone energy_assessment_id for a
                                     current-state (not just post-intervention) estimate
  estimated_avoided_energy_kwh
  emission_factor_id              # references SiteEmissionFactor (§10)
  estimated_co2e_kg
  disclaimer_version               # so the exact disclaimer text shown is itself versioned
```

`EnergyAssessment` and `EnergyOutcomeVerification` are new tables — no existing entity can
honestly absorb them without conflating energy with condition/decision assessments that mean
something structurally different. `CarbonEstimate` is a thin derived record; it could
alternatively be computed on read rather than persisted (matching `app.product_metrics`'s
"bespoke live query" pattern, §"What already exists") — recommended to persist it anyway, for
the same audit-trail reason `ConditionAssessment` is append-only rather than computed
on-the-fly, since a CO2e number a customer might reference later should be reproducible exactly
as originally shown, even if the site's emission factor is later updated.

## 15. Commercial value story

No fabricated figures anywhere in this section or in the product. Four value dimensions:

| Dimension | What it delivers |
|---|---|
| **Reliability** | Earlier visibility into lubrication deterioration — energy evidence is one more corroborating signal alongside rules/state estimation, catching what a single-threshold rule might miss |
| **Maintenance efficiency** | Condition-driven intervention, now with an energy-cost dimension attached to urgency — helps prioritize *which* developing issue to act on first |
| **Energy efficiency** | Identifies friction-related excess energy demand with an honest, evidenced confidence level, not a blanket "efficiency score" |
| **Sustainability** | Translates a *qualified* (data-quality-gated, comparability-checked) energy recovery into an estimated, provenance-tracked CO2e impact — never presented as audited accounting |

Personas:

- **Reliability engineer** — an additional, independent corroborating evidence source for
  diagnosis (§8), not a replacement for existing rule/state/ML evidence.
- **Maintenance manager** — urgency-weighted prioritization across open issues when energy
  cost and reliability risk coexist (§8's worked example).
- **Operations manager** — visibility into whether recent maintenance measurably changed
  energy behavior (§9), informing whether the intervention worked, not just whether the
  incident was closed.
- **Energy manager** — a friction-attributed view of otherwise-unexplained energy deviation
  across the fleet, distinct from general power-quality/demand-charge tooling this product
  does not attempt to replace.
- **Sustainability manager** — a defensible, provenance-tracked CO2e estimate to feed into
  broader (external, audited) reporting — explicitly framed as an input, not the audit itself.
- **Commercial/service organization** — a genuinely new, evidence-backed value story
  (efficiency + reliability, not reliability alone) for lubrication-service engagements,
  without ever promising a specific savings number this architecture cannot honestly support.

## 16. Future UX — design only, not implemented this pass

**Machine Detail — new section, "Energy & Efficiency Impact"**, following the same
"headline summary, technical detail behind a toggle" pattern `components/condition-evidence
.tsx` already established:

- Headline row: actual power, expected contextual power, deviation, attribution confidence —
  same visual language (`StatusPill`, `ConfidenceBadge`) already used for condition/ML
  evidence elsewhere.
- Chart: actual vs. expected power over time, with markers for condition-deterioration onset,
  incident creation, and maintenance completion — reusing the same annotated-telemetry pattern
  already built for the machine detail page's existing telemetry charts, not a new charting
  approach.
- Only rendered when `data_quality_state` permits a claim (§7) — an `EmptyState`/governance
  note otherwise, matching the same honesty discipline just built for ML evidence
  (`docs/` — see the ML evidence productization work already in this repo's history) rather
  than a blank or misleading chart.

**Fleet-level** (a `/ml`-style or `/data-quality`-style summary page, exact location TBD at
implementation time, not designed further here): assets with elevated energy residual,
estimated current excess demand fleet-wide, recently verified energy recoveries, estimated
CO2e impact — all counts traceable to real persisted `EnergyAssessment`/
`EnergyOutcomeVerification`/`CarbonEstimate` rows, following the exact "every number traces to
a real row" discipline the `/ml` page's fleet summary already established.

Metrics are only ever shown when the underlying evidence quality permits the claim being made
— never a placeholder number, never a greyed-out estimate presented as real.

## 17. Industrial safety / claims boundary

Energy optimization must never, under any circumstance this architecture enables:

- cause or recommend under-lubrication
- justify unsafe extension of a maintenance interval
- automatically reduce lubrication quantity or frequency solely to save energy

**A lower energy reading is not automatically better.** A machine that appears to draw less
power than expected is not necessarily healthier — it may indicate reduced load, a sensor
fault, or (worst case) reduced lubrication delivery that has not yet produced a measurable
friction penalty. Reliability and safety remain primary; energy evidence is additive
corroboration within the existing Condition/Decision Intelligence gates (§8), never an
independent authority, and — per CLAUDE.md's Workflow Intelligence boundary — nothing in this
architecture operates machinery, changes pump state, or modifies lubrication quantity. Any
lubrication-quantity or interval change stays a human-approved maintenance decision exactly as
it is today.

## 18. Architecture decision

**A. Architecture**: extend three existing subsystems (`app.baselines` for expected-power,
`app.condition_intelligence` for a new `EvidenceItem` source, `app.decision_intelligence` for
an urgency modifier) plus two genuinely new, small subsystems (a maintenance-verification
comparison service, and site-level emission-factor configuration). No new subsystem-scale
architecture is introduced — this is additive to the existing evidence pipeline, not a
parallel one.

**B. New entities/services required**:
- `SensorType.POWER` (domain enum)
- `EnergyAssessment`, `EnergyOutcomeVerification`, `CarbonEstimate` (new persisted models, §14)
- `SiteEmissionFactor` (new persisted config, §10)
- A new `POWER`-baselined feature set (`app.features`, follows existing catalog pattern)
- An `EnergyIntelligenceService` (or similarly named, `app.energy_intelligence` or nested
  under an existing module — naming/placement is an implementation-time decision) computing
  §4–§6
- A maintenance-verification comparison service (§9)
- A carbon-estimation service (§10), reusing `SiteEmissionFactor`

**C. APIs required** (read-only query APIs, mirroring the existing `app.ml`/
`app.condition_intelligence` route shape — `GET .../machines/{id}/latest`,
`GET .../fleet-latest`, `GET .../machines/{id}/history`):
- `GET /energy/machines/{id}/latest`, `/fleet-latest`, `/machines/{id}/history`
- `GET /energy/machines/{id}/outcome-verifications` (per maintenance case)
- `GET /energy/machines/{id}/carbon-estimates`
- `GET/PUT /configuration/sites/{id}/emission-factor` (admin-gated, following existing RBAC
  patterns)

**D. Simulator changes required**: a new machine-driveline `power_kw` physics model per §12 —
design specified, not implemented.

**E. ML model opportunity**: `EXPECTED_ENERGY_REGRESSION` — assessed and explicitly deferred
(§13); the contextual baseline is the correct v1.

**F. Integration into existing layers**: §8 (Condition/Decision), reusing `EvidenceItem` and
the criticality-modifier decision pattern with zero schema change to either.

**G. Implementation order** (minimal-risk-first, each step independently shippable and
independently valuable — not a single big-bang release):

1. `SensorType.POWER` + simulator physics extension (§12) + a `POWER`-baselined feature set —
   ships real, contextual expected-power data with no product-facing claim yet.
2. `EnergyAssessment` + the expected-energy/residual computation service (§4–§5) — internal/
   API-only, still no UI, provable against synthetic data before anything is shown.
3. Lubrication attribution (§6) + `ENERGY_RESIDUAL` `EvidenceItem` wiring into
   `ConditionEngine` (§8) — evidence-only, condition synthesis behavior change reviewed and
   tested exactly as any other evidence-source change would be (full backend suite, per this
   repo's own established practice for condition-synthesis changes).
4. `DecisionEngine` urgency-modifier wiring (§8).
5. `EnergyOutcomeVerification` + the maintenance-verification service (§9) — depends on step 2
   existing for at least one full maintenance-case lifecycle.
6. `SiteEmissionFactor` + `CarbonEstimate` (§10–§11) — the one step with no dependency on
   condition/decision wiring at all; could ship in parallel with steps 3–5 if useful.
7. Frontend (§16) — after backend data is real and stable, not before; follows this repo's own
   "backend proves it could exist, frontend proves it's useful" ordering (CLAUDE.md).
8. `EXPECTED_ENERGY_REGRESSION` (§13) — only if real (not synthetic) field data later shows
   the contextual baseline's context granularity is materially insufficient.

**H. Validation strategy**: unit tests for the expected-energy/residual math and attribution
derivation (pure functions, same testing shape as `synthesis.py`'s own test suite); simulator
physics changes validated the same way `simulator/tests/` already validates existing physics
(deterministic scenario runs, known expected direction of effect); condition-synthesis
integration changes run through the **full backend test suite** (not just
`condition_intelligence`/`rules_engine`), per this repo's own established practice whenever
condition-synthesis inputs change; no field validation is possible or claimed at this stage —
CLAUDE.md's Industrial Adoption Boundary applies to every number this capability ever produces
until real machine histories exist.

## 19. Cross-references

- `docs/CONDITION_INTELLIGENCE.md` — the evidence/strength-tier discipline this design extends
- `docs/DECISION_INTELLIGENCE.md` — the criticality-modifier precedent §8 follows
- `docs/PRODUCT_METRICS.md` — the honest-labeling discipline §10–§11 follow
- `docs/FAILURE_MODE_CATALOG.md` — the failure modes energy evidence corroborates, never
  replaces
- `docs/SIMULATOR.md` — the existing physics this design extends in §12
- `TECHNICAL_DECISIONS.md` ADR-176 — the architecture decisions from this document worth
  recording permanently (reuse-vs-new-surface calls in the table above)
