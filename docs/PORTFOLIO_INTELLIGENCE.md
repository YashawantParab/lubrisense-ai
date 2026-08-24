# Portfolio Intelligence — Organization / Site / Area Performance

**Portfolio Intelligence Pass 1** — a post-roadmap capability extension (ADR-177), not a
new numbered phase. Builds the organization-level product-data foundation an eventual
enterprise APM-style experience needs; does **not** implement that frontend.

## Purpose

Every intelligence layer this platform has built so far (Condition, Decision, Energy,
Lubrication Attribution, Energy Outcome Verification, Carbon) answers questions about
*one machine*. This capability answers the question none of them can:

> What is happening across my industrial organization?

`app.portfolio.services.portfolio_service.PortfolioService` is a pure **read model** —
it aggregates already-persisted evidence from every existing intelligence layer into
organization/site/area rollups. It computes nothing new about any machine's condition,
energy, or carbon state; it never writes to any table.

## Hierarchy reused, not duplicated

Inspected first (design doc §"inspect existing hierarchy"), extended nowhere:
`Tenant → CustomerAccount → Site → Plant → ProductionLine → Machine` already exists
(`docs/ASSET_HIERARCHY.md`) and is what this capability's "Organization → Site → Asset"
drilldown maps onto directly — **Organization is Tenant**, matching every other
tenant-wide read model in this codebase (`FleetOverview`, `NorthStarResult`,
`fleet_latest`).

**No dedicated "Area" model exists, and none was added.** `Machine.metadata_["area"]` —
already seeded for the ten curated demonstration machines (Pass 37+) — is reused as the
area key directly. For a machine with no explicit `area` metadata (the platform's
uncurated background fleet), the area falls back to `Plant.plant_type` (a real,
already-seeded free-text field, e.g. "Crushing & Screening"), then finally to the literal
string `"Unspecified Area"`. This means a curated machine's specific area label (e.g.
"Crushing") and an uncurated machine's plant-level fallback (e.g. "Crushing &
Screening") can appear as two distinct area buckets even though they describe similar
equipment — a real, honest consequence of using two genuinely different (but both real)
data sources, not a bug to paper over with fabricated metadata.

**Area is an organization-wide grouping, not nested under one site** — `GET
/api/v1/performance/areas` returns every area across the whole tenant; an
`AreaPerformanceSummary.site_codes` field lists which sites contribute to it. This
matches how the product itself frames areas (design doc §"area performance":
"Bulk Material Handling", "Crushing", etc. as cross-cutting equipment categories, not
site-specific subtrees).

## Architecture

`backend/app/portfolio/`:

- `domain/action_readiness.py` — `derive_action_readiness()`, pure.
- `domain/priority.py` — `derive_priority()`, pure, versioned (`POLICY_VERSION`).
- `domain/energy_bucket.py` — `derive_energy_bucket()`, pure.
- `domain/maintenance_outcome.py` — `derive_maintenance_outcome_bucket()`, pure.
- `domain/data_trust.py` — `overall_quality_state()` / `derive_data_trust_category()`,
  pure; mirrors `ConditionEngine._overall_quality_state`'s own worst-of policy rather
  than importing across a module's private boundary.
- `models.py` — frozen dataclasses (`MachineSnapshot`, `OrganizationPerformanceSummary`,
  `SitePerformanceSummary`, `AreaPerformanceSummary`, `AttentionAsset`, `RecentOutcome`,
  …) — never ORM/persisted, mirrors `app.customer_services.models`'s own convention.
- `services/portfolio_service.py` — `PortfolioService`, the orchestration layer.

## Query-count discipline

`PortfolioService._load_data()` issues **nine tenant-wide queries, fixed regardless of
fleet size**: one hierarchy join (`Machine ⋈ ProductionLine ⋈ Plant ⋈ Site`), one latest
condition per machine, one all-incidents, one all-maintenance-cases, one fleet
sensor-quality read, and one `fleet_latest` call each for `EnergyAssessment`,
`LubricationEnergyAttribution`, `EnergyOutcomeVerification`, `CarbonImpactEstimate` —
every one of those `fleet_latest` methods already existed (Pass 1–4). Every public method
on `PortfolioService` calls `_load_data()` **exactly once per request** and reuses its
`_PortfolioData` bundle for every section computed from it, instead of re-querying the
same tenant-wide table per section. Measured directly (SQLAlchemy `before_cursor_execute`
event count) against a synthetic 10-machine and 50-machine tenant: **9 queries in both
cases** — confirms no N+1 query pattern.

## Aggregation principles

Every count/sum in every summary object traces back to real machine-level records
(`MachineSnapshot` rows). Enforced throughout:

- An asset is never counted twice because it has multiple open incidents — attention/
  condition/data-trust counts are always "how many *machines*", never "how many
  incidents".
- A denominator always travels with its numerator, never an implicit "of the whole
  fleet" — e.g. `CarbonSection.carbon_estimate_available_count` is always read against
  `CarbonSection.qualified_recovery_count`, never against the fleet total.
- `qualified_avoided_energy_kwh_total`/`estimated_co2e_kg_total` sum **only** machines
  whose `EnergyOutcomeVerification.energy_outcome_status == QUALIFIED_RECOVERY` (Pass 3's
  own gate) and, for carbon, whose linked `CarbonImpactEstimate.estimate_status` is
  `ESTIMATE_AVAILABLE`/`LIMITED_ESTIMATE` (Pass 4's own gate). An `ATTRIBUTION_SUPPORTED
  _OPPORTUNITY` or `POSSIBLE`/`MODERATE`/`STRONG` attribution alone is never summed as
  avoided energy — it has no `estimated_avoided_energy_kwh` to sum in the first place.
- Nothing here is annualized or extrapolated — every total is over the qualifying
  observed period only, exactly as Pass 3/4 computed it.
- Missing data is never converted to zero silently — `INSUFFICIENT_ENERGY_DATA`/
  `NOT_YET_ASSESSED`/`FACTOR_NOT_CONFIGURED` are their own counted categories, always
  visible in a distribution dict, never folded into "normal"/zero.

## Action-readiness aggregation

`ActionReadinessState` — `MONITORING_ONLY` / `HUMAN_ACTION_REQUIRED` / `ASSESSMENT
_BLOCKED` / `DATA_LIMITED` / `NOT_YET_ASSESSED`. Deliberately does **not** offer a
"simulation-only auto-eligible" or "blocked by safety/interlock" state: this reference
architecture has no automated-control loop or physical-interlock signal to derive either
from (CLAUDE.md's Workflow Intelligence boundary — every action already requires human
review, unconditionally), and introducing either value without a real underlying signal
would fabricate a capability the platform does not have. "Manual action required" and
"human approval required" collapse into the single real state `HUMAN_ACTION_REQUIRED`
for the same reason — this architecture cannot currently distinguish them.

## Attention prioritization

`PortfolioPriority` — `CRITICAL_ATTENTION` / `HIGH_ATTENTION` / `ATTENTION` / `MONITOR` /
`DATA_LIMITED` — a deterministic, explainable, versioned categorical policy
(`app.portfolio.domain.priority`, `POLICY_VERSION = "1"`), never a fabricated numeric
score (mirrors `CustomerOperationalStatus`'s own "categorical precedence, not an opaque
score" discipline). Every result carries `reasons: list[str]` in the platform's own
evidence language, never a bare number.

**Reliability/safety evidence is always primary.** Condition severity, unresolved
incidents, maintenance urgency, and asset criticality (a modifier only — a healthy
`CRITICAL`-criticality asset stays at `MONITOR`; criticality only *escalates* an already
-justified `HIGH_ATTENTION` to `CRITICAL_ATTENTION`, it never manufactures attention on
its own) determine the base priority. **Energy/carbon evidence is strictly
supplementary**: an elevated-energy machine with no other concern is floored at
`ATTENTION` and never higher — energy evidence can raise `MONITOR` to `ATTENTION`, but it
can never push a machine's priority above what reliability evidence alone already
justifies, and it never lowers an existing higher priority either. `ASSESSMENT_BLOCKED`/
`NOT_YET_ASSESSED` action-readiness states short-circuit straight to `DATA_LIMITED`,
regardless of any other signal — reported honestly rather than guessed at.

## Energy portfolio semantics

`EnergyPortfolioBucket` (`app.portfolio.domain.energy_bucket`) combines a machine's
*current* `EnergyAssessment`/`LubricationEnergyAttribution` state with its most recent
`EnergyOutcomeVerification` (if any) into one bucket per machine:

```
NORMAL_ENERGY_BEHAVIOR
ACTIVE_ELEVATED_ENERGY
ATTRIBUTION_SUPPORTED_OPPORTUNITY
OUTCOME_AWAITING_VERIFICATION
QUALIFIED_ENERGY_RECOVERY
INCONCLUSIVE_OUTCOME
OUTCOME_DETERIORATED          # principled addition — see below
INSUFFICIENT_ENERGY_DATA
```

`OUTCOME_DETERIORATED` is one bucket beyond the seven literally requested: folding a
`DETERIORATED` energy outcome into `INCONCLUSIVE_OUTCOME` would misrepresent a clear
negative signal as merely ambiguous.

**Two required, load-bearing distinctions, preserved exactly and regression-tested**
(`tests/portfolio/test_energy_bucket_policy.py`):

- **Kiln ID Fan IDF-01** (`L2-E915-M008`) has real `ELEVATED_ENERGY_DEMAND` and real
  `POSSIBLE` lubrication attribution, but no completed maintenance intervention yet —
  `ATTRIBUTION_SUPPORTED_OPPORTUNITY`, never described as a recovery. It remains,
  correctly, an *active opportunity*.
- **Bucket Elevator BE-201** (`L1-7F84-M016`) has a real `QUALIFIED_RECOVERY`
  `EnergyOutcomeVerification` — `QUALIFIED_ENERGY_RECOVERY`. Its `pre_attribution_level`
  is `NO_EVIDENCE` (Pass 3's own honest, documented limitation of *when* attribution runs
  in this seed pipeline), so its `lubrication_association_status` is
  `QUALIFIED_ENERGY_RECOVERY` (claim-hierarchy Level 2), **never**
  `LUBRICATION_ASSOCIATED_RECOVERY` (Level 3) — this portfolio layer reads that field
  straight through from Pass 3 and never re-derives or upgrades it.

### Opportunity vs. outcome

- **Energy opportunity** = `ACTIVE_ELEVATED_ENERGY` or `ATTRIBUTION_SUPPORTED
  _OPPORTUNITY` — an active elevated-energy state, with or without supporting
  attribution evidence, no completed intervention required.
- **Outcome** = a completed, (structurally simplified — see "Known limitations")
  relevant intervention with a verification attempt: `OUTCOME_AWAITING_VERIFICATION`,
  `QUALIFIED_ENERGY_RECOVERY`, `INCONCLUSIVE_OUTCOME`, or `OUTCOME_DETERIORATED`.
- **Qualified outcome** = `QUALIFIED_ENERGY_RECOVERY` only.

Opportunities are never summed into `qualified_avoided_energy_kwh_total` — only
`QUALIFIED_ENERGY_RECOVERY` machines (which have a real, Pass-3-computed
`estimated_avoided_energy_kwh`) contribute to that total.

## Maintenance outcome aggregation

`MaintenanceOutcomeBucket` (`app.portfolio.domain.maintenance_outcome`) — completion is
never represented as automatic success:

```
OPEN_ACTION
COMPLETED_OUTCOME_NOT_ASSESSED
COMPLETED_QUALIFIED_RECOVERY
COMPLETED_PROBABLE_RECOVERY   # principled addition — see below
COMPLETED_NO_MATERIAL_CHANGE
COMPLETED_INCONCLUSIVE
COMPLETED_DETERIORATED
```

`COMPLETED_PROBABLE_RECOVERY` is one bucket beyond the six literally requested:
collapsing a `PROBABLE_RECOVERY` energy outcome into either `COMPLETED_QUALIFIED
_RECOVERY` or `COMPLETED_INCONCLUSIVE` would either overstate or discard real Pass-3
evidence — the same discipline that keeps `EnergyOutcomeStatus.PROBABLE_RECOVERY`
distinct from `QUALIFIED_RECOVERY` in Pass 3 itself. A `CANCELLED` `MaintenanceCase` maps
to `None` and is excluded from outcome counts entirely — it was never completed and is
not "open" either, so it is never forced into either bucket.

"Overdue" (`MaintenanceSection.overdue_actions`) is a deliberately conservative,
documented definition given this reference architecture has no dedicated due-date/SLA
tracking system: a non-terminal case recommended for `NOW` that has not even started, or
whose own `planned_for` date has passed.

## Data-trust rollup

`DataTrustCategory` (`app.portfolio.domain.data_trust`) — `DECISION_EVIDENCE_TRUSTED` /
`CONFIDENCE_REDUCED` / `ASSESSMENT_BLOCKED` / `ACTION_BLOCKED` — a categorical, per
-machine worst-of judgment over that machine's own sensors (mirrors `ConditionEngine
._overall_quality_state`'s exact three-tier policy), **never derived from mean sensor
quality across the fleet.** `ACTION_BLOCKED` outranks `ASSESSMENT_BLOCKED`/`CONFIDENCE
_REDUCED` when a data-quality limitation co-occurs with an open incident/maintenance
case — the more urgent framing.

`DataTrustSection.critical_assets_limited` counts `HIGH`/`CRITICAL`-criticality machines
in `ASSESSMENT_BLOCKED`/`ACTION_BLOCKED` specifically — a site with 95% trusted sensors
but one blocked critical asset still surfaces that limitation as its own explicit count,
never averaged away.

## Carbon portfolio semantics

`CarbonSection.estimated_co2e_kg_total` sums **only**
`CarbonImpactEstimate.estimated_co2e_kg` for machines whose linked outcome is
`QUALIFIED_RECOVERY` **and** whose carbon estimate status is `ESTIMATE_AVAILABLE`/
`LIMITED_ESTIMATE` — `carbon_estimate_available_count` is always the count actually
summed, and `qualified_recovery_count` is the honest denominator it is judged against
(never the whole fleet). `carbon_outcomes_missing_factor` separately counts qualified
outcomes whose carbon estimate is `FACTOR_NOT_CONFIGURED`/`FACTOR_NOT_APPLICABLE` — so
"we have a real qualified recovery but no carbon estimate for it" stays visible instead
of silently vanishing into a zero total. Product copy for this total is always "Estimated
energy-related CO2e impact from qualified observed outcomes" (or a materially equivalent
shorter form) — never "total carbon saved" (Pass 4's own claim-language boundary,
unchanged here).

**A `CarbonImpactEstimate` only ever counts here if it is linked to the machine's own
current `EnergyOutcomeVerification`** (`carbon.energy_outcome_verification_id ==
outcome.id`) — a stale carbon estimate computed against an older, superseded outcome is
never attributed to the machine's current state.

## Recent outcomes

Four distinct, provenance-carrying event types (each machine's *current* latest state,
not a full historical audit log): `CONDITION_RESOLVED`/`CONDITION_IMPROVING` (from the
latest `ConditionAssessment`'s own `lifecycle_state`), `MAINTENANCE_COMPLETED` (from
`MaintenanceCase.state == COMPLETED`), `QUALIFIED_ENERGY_RECOVERY` (from a
`QUALIFIED_RECOVERY` `EnergyOutcomeVerification`), `CARBON_ESTIMATE_PRODUCED` (from an
`ESTIMATE_AVAILABLE`/`LIMITED_ESTIMATE` `CarbonImpactEstimate`). Each `RecentOutcome`
carries its own `outcome_type` and `provenance` — never mixed into one undifferentiated
feed a reader has to guess the meaning of. Deliberately deferred (out of scope for this
pass): `data-quality blockage resolved` and `commissioning completed` events — this
reference architecture has no cheap, already-available "just resolved" signal for either
without an additional historical query this pass's query-count discipline intentionally
avoids adding.

## API

- `GET /api/v1/performance/organization` → `OrganizationPerformanceSummary`
- `GET /api/v1/performance/sites` → `list[SitePerformanceSummary]`
- `GET /api/v1/performance/sites/{site_id}` → `SitePerformanceSummary`
- `GET /api/v1/performance/areas` → `list[AreaPerformanceSummary]`
- `GET /api/v1/performance/areas/{area_key}` → `AreaPerformanceSummary`
- `GET /api/v1/performance/attention?limit=` → `list[AttentionAsset]`
- `GET /api/v1/performance/outcomes?limit=` → `list[RecentOutcome]`

All seven require `Permission.METRICS_READ` (Phase 24) and are tenant-scoped via the
existing `X-Tenant-ID` mechanism (`app.api.deps.get_current_tenant`) — the same RBAC/
isolation convention `app.api.v1.fleet`/`site_overview`/`customer_overview` already use.
Read-only: no route here ever triggers computation of a new `EnergyAssessment`/
`LubricationEnergyAttribution`/`EnergyOutcomeVerification`/`CarbonImpactEstimate` — every
number is read from what each capability's own service already persisted.

## Future frontend contract

Response objects were shaped for later visualization components without being tailored
to any one chart library: `OrganizationPerformanceSummary`'s eight sections (portfolio,
reliability, maintenance, action_readiness, energy_efficiency, carbon, data_trust) map
directly onto "organization KPI strip" + distribution-chart components;
`SitePerformanceSummary`/`AreaPerformanceSummary` support "site comparison cards" and
drilldown; `AttentionAsset`/`RecentOutcome` support an "attention queue" and "recent
outcomes" feed. No chart is implemented in this pass, and no organization-level frontend
redesign happens here — that is an explicitly separate, controlled productization pass.

## Known limitations

- `EnergyPortfolioBucket.OUTCOME_AWAITING_VERIFICATION`/`MaintenanceOutcomeBucket`'s
  "has completed maintenance" signal uses "any `COMPLETED` `MaintenanceCase` exists for
  this machine", not `app.energy.domain.outcome.determine_maintenance_relevance`'s own
  structured-action relevance check (which requires a per-case `MaintenanceAction` join)
  — a deliberate simplification to keep this portfolio-wide bucket derivation's query
  count fixed. An irrelevant completed case (e.g. `VERIFY_SENSOR`) can therefore appear
  as `OUTCOME_AWAITING_VERIFICATION` even though `EnergyOutcomeService` itself would
  never treat it as a qualifying intervention.
- Area fallback to `Plant.plant_type` (see "Hierarchy reused" above) means a curated
  machine's specific area label and an uncurated machine's plant-level fallback can
  appear as separate area buckets for conceptually related equipment.
- `attention_queue`/`organization_summary` recompute the whole fleet snapshot per request
  (no caching) — fine at reference/demo scale (`docs/PERFORMANCE.md`'s own target scale),
  would want a cached/materialized rollup at real industrial fleet scale.
