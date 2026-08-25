# Product Experience (Phase 28/29)

## Purpose

Phases 1–27 built a real backend and a collection of technical/developer validation
pages — one per backend domain area, useful for verifying each phase but not a coherent
industrial product. Phase 28 turned that collection into an actual product experience;
Phase 29 refined it (loading/empty/error states, terminology, accessibility, small
details). This document records the resulting information architecture, the machine
detail page design (the product's most important page), the shared component/
terminology system, and what is known to still be rough.

Every value shown anywhere in the product still comes from a real backend API — this
sprint added no hardcoded telemetry, no fake health scores, no mocked responses.

## Information architecture

Primary navigation (the product), as of Enterprise Experience Pass A (see its own
section below — supersedes the flat list this section originally described):

`Organization → Sites → Fleet → Incidents → Maintenance → Action Readiness → Knowledge
→ Assistant → Metrics`

Secondary "System" navigation (technical/developer inspection, still fully functional,
visually demoted rather than removed — see ADR-158):

`Configuration → Audit → Asset Hierarchy → Sensor Inventory → Data Quality → Baselines
→ Rule Findings → Features → ML → State Estimation → Intelligence (raw) → System Status`

`/` redirects to `/performance/organization` (previously `/overview` — Phase 28 through
Enterprise Experience Pass A; `/overview` itself is preserved, unlinked from primary
nav, for its fleet-asset-level walkthrough content, and is one click away from the
Organization Command Center's own footer link). The application shell
(`components/app-shell.tsx`) is a fixed sidebar (mobile: hamburger overlay) showing
product identity, a live `SystemStatusDot` (backend readiness), and a demo
identity/role switcher in the top bar.

## The three intelligence layers, made visible

CLAUDE.md's three intelligence layers (Machine & Sensor / Decision / Workflow) are
rendered as three explicit, visually separated columns on the machine detail page —
never collapsed into one undifferentiated "AI says X" block:

- **Machine Intelligence** — what the raw evidence sources report: rule-finding count,
  ML evidence count, state-estimate count, baseline readiness. Answers *what is
  happening, physically*.
- **Decision Intelligence** — the synthesized recommendation: recommended action,
  window, priority, human-review flag, risk if deferred. Answers *what does it mean and
  what should we do*.
- **Workflow Intelligence** — the response state: active incident (if any), linked
  maintenance case, an "Ask Assistant" entry point. Answers *how do we act*.

## The machine detail page

`/machines/[machineId]` is the product's most important page (CLAUDE.md: "Every major
screen should quickly answer WHAT IS HAPPENING? WHY? WHAT MAY HAPPEN NEXT? WHAT SHOULD
I DO?"). Section order, top to bottom (see ADR-159 for the reasoning):

1. Header — machine name/asset code/type, breadcrumb, criticality + operational-status
   badges, "Ask Assistant" action
2. Operational status strip
3. Three-column Machine / Decision / Workflow Intelligence summary
4. "What may happen next?" — the prognostic forecast, or an explicit
   **NO RELIABLE FORECAST** state (never an empty chart or a fabricated number) when
   insufficient state-estimate history exists
5. Evidence panel — supporting/contradicting evidence and data-trust summary in plain
   language first; a "Show technical detail" toggle reveals rule-finding ids, model/
   policy versions, condition id
6. Telemetry — one `TelemetryChart` per measurement type actually reported by this
   machine's sensors, each with a baseline-range overlay (when a `BaselineProfile`
   exists) and a data-quality-limitation callout when relevant
7. Device / Configuration (Phase 30/31) — current device snapshots and an expandable
   change history
8. Asset details — bearings, lubrication system, sensor inventory; collapsed behind a
   "Show" toggle, since this is the most implementation-facing content on the page and
   must never appear before the product-level sections above it

Nothing on this page is hardcoded: every section renders a real, honest empty state
(`"No telemetry received yet"`, `"No active incident"`, `"Not enough evidence has been
gathered to assess this machine"`) when the underlying data genuinely doesn't exist yet
— never a fabricated placeholder value.

## Shared components and terminology

- `components/badges.tsx` — one badge component per status vocabulary (severity,
  confidence, priority, data quality, incident state, maintenance state, technician
  feedback, customer status, evidence provenance, human-review, commissioning status,
  capability level, device compatibility), all thin wrappers around a shared
  `StatusPill` + `lib/terminology.ts` tone function. Using these everywhere is what
  keeps a "HIGH" confidence badge and a "HIGH" priority badge visually distinct even
  though both are the same source string.
- `lib/terminology.ts` — `humanize()` (`SNAKE_CASE` → `Title Case`), `shortId()`, and
  every tone-mapping function, in one place. Before this sprint, `/intelligence` and
  `/incidents` each had their own slightly-different copy of this logic; that
  duplication was the direct cause of confidence/severity color meanings drifting apart
  between pages.
- `components/page-header.tsx`, `empty-state.tsx`, `section-card.tsx`,
  `relative-time.tsx`, `data-state.tsx` (loading spinner / `onRetry` / human-readable
  error text) — the standard building blocks every rebuilt page composes from.
- `hooks/use-page-title.ts` — every route now sets a real, specific
  `document.title` (`"Fleet · LubriSense AI"`, not a generic "Next.js App").

## Errors, loading, and empty states

- Loading: `DataState`'s spinner, consistently, on every data-fetching section.
- Empty: `EmptyState` with a specific, honest message per context — never a blank div.
- Errors: `DataState.readableMessage()` trusts the backend's own `ApiError.message`
  (already human-readable per Phase 23 backend hardening) and never renders raw
  FastAPI/Pydantic validation detail or a stack trace; an `onRetry` action is offered
  wherever a retry is meaningful (a failed query), not offered where it wouldn't be
  (a completed mutation).

## Auth / role UX

The top-bar "Demo identity" selector switches among the six demo roles
(VIEWER/TECHNICIAN/RELIABILITY_ENGINEER/PLANT_MANAGER/DATA_SCIENTIST/ADMIN), issuing a
real `POST /auth/demo-login` token per selection. `lib/permissions.ts` mirrors the
backend's role→permission matrix to drive `can(permission)` hide/disable checks on
incident/maintenance/commissioning action buttons (see ADR-160). **This is
presentation-only.** The backend's `require_permission` dependency is the only actual
security boundary — verified directly, not just documented, by attempting a
VIEWER-role mutation against a route the frontend already hides the button for and
confirming the backend still returns 403.

## Small-detail quality sweep (Phase 29 §29.11)

Grepped the entire `frontend/src` tree for `TODO`/`FIXME`/`HACK`/`TEMP`,
`Lorem ipsum`/placeholder text, `example.com`, `console.log`, `alert(`, literal
`"undefined"` strings, and hardcoded `localhost` outside of legitimate env-fallback
config. No violations found. A repository-wide prohibited-name scan (frontend, backend,
docs) found no real-company or real-vendor references — every demo customer/site/
gateway name is fictional (Ridgeline, Harborview, Millbrook, Eastgate, Dornbach).

## Responsiveness and accessibility

Desktop-primary, verified at 1440/1280/1024px (the sidebar shell and every rebuilt page
use flex/grid layouts that reflow, not fixed pixel widths); the mobile hamburger overlay
gives basic tablet/mobile sanity but is not the design target. Accessibility: semantic
heading hierarchy on every page, visible focus states on interactive elements, status
communicated by badge text/label in addition to color (never color-only), form labels
on every input in the commissioning wizard.

## Enterprise Experience Pass A — Organization Command Center

Transforms the product's default landing experience from an asset-level fleet overview
into an organization-level reliability/maintenance/energy/carbon/data-trust command
center, built entirely on the Portfolio Intelligence read model (ADR-177,
`docs/PORTFOLIO_INTELLIGENCE.md`). This pass is frontend-first: it consumes
`GET /api/v1/performance/*` exactly as that API already shaped its responses, adding
only one small, genuinely-needed backend field (`organization_name`, sourced from
`Tenant.name` — the Organization Header needs a real name, and no existing endpoint
exposed one) and one backend routing fix (below).

### Pages and hierarchy

`ORGANIZATION → SITE → AREA → ASSET → INTELLIGENCE → ACTION → OUTCOME`, realized as:

- `/performance/organization` — the new home page (`app/page.tsx` redirects here).
  Organization header (real tenant name, as-of, site/asset counts, provenance) → KPI
  strip → fleet reliability distribution (`PortfolioPriority`, not condition type — the
  same categories the attention queue ranks by) → site performance table → priority
  attention → energy & efficiency → carbon → maintenance/action-readiness (paired) →
  data trust → recent outcomes.
- `/performance/sites` — the same comparative site table as its own dedicated page (nav
  entry "Sites"), for a user who wants the site list without the full command center.
- `/performance/sites/[siteId]` — Site Detail. Deliberately not "the organization page
  with filtered numbers": adds a condition breakdown (dynamic, open-vocabulary
  `condition_distribution` — see below), an "Areas at this site" table, and omits
  fields the site response genuinely doesn't carry (no full energy-bucket distribution,
  no `critical_assets_limited` — the site response doesn't expose them; the relevant
  panels render their summary-only variant rather than fabricating the missing detail).
- `/performance/areas`, `/performance/areas/[areaKey]` — Areas are **organization-wide**
  rollups (`AreaPerformanceSummary.site_codes` — a real seeded area like "Pyroprocessing"
  or "Bulk Material Handling" is active at more than one site). There is no
  site-scoped area sub-aggregate in the backend, so a "site → area" click-through always
  lands on the same organization-wide Area Detail page, with an explicit disclosure
  ("Organization-wide rollup for this area — active at HARBOR, RIDGE. Figures below
  span all of these sites, not one alone.") rather than silently implying a site-scoped
  number the backend does not compute. This was a deliberate choice between the task's
  two allowed options (dedicated page vs. filtered view) — see
  `AreaPerformanceTable`'s own docstring.
- `/performance/attention` — the full `GET /performance/attention?limit=200` queue;
  `top_attention_assets` embedded in the organization/site responses caps at 10, so
  every "View full queue" link needs a real destination rather than dead-ending.
- Machine Detail (`/machines/[machineId]`) — not redesigned this pass, but its
  breadcrumb now reads `Organization / Site / Area / Asset` (resolving the containing
  site via the same tenant-wide hierarchy tree the Fleet page already fetches, so it's
  typically already warm in the React Query cache) instead of the old flat `Fleet /
  Asset`.

### Condition breakdown: fixed buckets vs. open vocabulary

Two different components exist for what looks like the same chart, deliberately:
`ReliabilityPanel` renders the organization's fixed, backend-versioned
`PortfolioPriority` distribution (five categories, always present); `ConditionBreakdown`
renders the site/area responses' raw `condition_distribution` (an open, dynamic
`ConditionType` vocabulary — a site could show any subset of the domain's condition
types). Forcing the second into the first's fixed-category chart would either drop real
condition types or fabricate a mapping the backend never asserted; they use different
color strategies for the same honest reason (`PRIORITY_BAR_CLASS`'s fixed palette vs.
`toDynamicSegments`'s count-sorted, purely-decorative cycling palette — every legend row
still repeats the label/count as text, so color is never the only signal).

### Energy, carbon, and maintenance-outcome terminology

`EnergyEfficiencyPanel` renders "Active opportunities" and "Qualified outcomes" as two
visually distinct panels (amber vs. emerald), never one "Savings" heading — an
IDF-01-shaped asset (elevated demand, attribution-supported, no completed intervention)
only ever populates the left panel; a BE-201-shaped asset (a real qualified recovery)
only the right, with its observed kWh explicitly captioned "never annualized or
projected forward." `CarbonPanel` never renders "0 kg CO2e" as if it were a real zero —
`estimated_co2e_kg_total === 0` with no qualifying outcome renders an explicit
"not a zero impact" explanation instead, and every carbon figure carries the required
tooltip text ("Operational estimate derived from qualified observed energy recovery and
configured electricity emission factor"). `MaintenanceOutcomesPanel` renders the
seven-bucket `MaintenanceOutcomeBucket` distribution so a completed case never reads as
automatic success — `COMPLETED_QUALIFIED_RECOVERY` and `COMPLETED_DETERIORATED` are
visually distinct (emerald vs. red), not folded into one "Completed" pill.

### Cross-links

Attention asset → Machine Detail; Site row → Site Detail; Area → Area Detail; a
`DATA_LIMITED`-priority (or never-assessed) attention-queue entry → Data Quality
filtered for that machine (`/data-quality?machine=<id>`, reusing the existing page's
own `?machine=` filter rather than inventing a new one). "Energy opportunity → machine
energy detail" was deliberately **not** added: Machine Detail has no energy-evidence
surface today (Lubrication Efficiency Intelligence, ADR-176, is backend-only, matching
the task's own "if current surface exists" qualifier) — adding a link to a page that
doesn't exist would be a dead end, so none was created.

### A real bug found via manual click-through, not by the test suite

`GET /performance/areas/{area_key}` used a plain FastAPI string path converter. Every
area name the automated test suite used ("Crushing", "Grinding") was slash-free, so it
never caught that a real seeded area name containing "/" ("Metals / Rolling") 404s once
the browser percent-encodes it — Starlette decodes `%2F` before route matching, so a
plain converter sees three path segments instead of one. Found by actually clicking
through the rendered Areas table in a browser, not by reasoning about the route in the
abstract. Fixed with `{area_key:path}` on the backend
(`backend/app/api/v1/performance.py`) plus a regression test seeding a real
slash-containing area name (`test_area_performance_by_key_with_slash_in_name`); on the
frontend, `AreaDetailPage` explicitly `decodeURIComponent`s the raw Next.js route param
before use, since Next.js leaves a single dynamic segment containing an encoded slash
undecoded rather than resolving it the way it resolves a plain `%20`.

### Testing infrastructure

No frontend test runner existed anywhere in this repository before this pass. Added
Vitest + `@testing-library/react` + jsdom (`frontend/vitest.config.mts`,
`npm run test`) — the minimal, standard choice for a client-heavy Next.js App Router
codebase, not a heavier framework this repo has no other use for. Coverage this pass is
intentionally scoped to pure logic (`lib/portfolio.ts`'s segment/ordering functions,
the five new `lib/terminology.ts` tone functions) and every new **presentational**
component (`SegmentedDistributionBar`, `KpiStrip`, every `components/portfolio/*`
panel/table, the new portfolio badges) — 62 tests across 17 files, all passing. Pages
that call `useQuery` hooks directly (`OrganizationPerformancePage`, `SiteDetailPage`,
etc.) are not unit-tested — they were verified manually in a real browser against a
live backend/Postgres instead (see below) — unit-testing them would need a
`QueryClientProvider` mocking layer this pass did not build.

### Manual verification

Ran a local backend (`uv run uvicorn app.main:app --port 8001`, real Postgres — the same
database the hosted-demo `docker compose` stack uses) and a local frontend dev server
(`next dev -p 3001`, pointed at that backend) alongside the running `docker compose`
stack, without touching it. Visually inspected in a real Chrome tab at 1568×769:
Organization Command Center (every section, including empty-state and critical-asset-
limited banners), Sites index, Site Detail (Harborview — areas table, empty maintenance/
outcomes states), Area Detail (both a single-site area and the multi-site "Metals /
Rolling" area, confirming the slash-routing fix), the full Priority Attention queue
(confirming the Data Quality cross-link), and the Machine Detail breadcrumb
(Organization / Harborview Site / Pyroprocessing / Kiln ID Fan IDF-01, each segment
verified clickable). Dark-mode was not pixel-verified — the environment's
`resize_window`/viewport tooling did not reliably change the tab's actual CSS viewport
in this session, so narrow-viewport (mobile) layouts were reviewed at the code level
only (every new `SectionCard`/table uses the same responsive `sm:`/`lg:` grid classes
and `overflow-x-auto` table wrapper already verified working elsewhere in this app,
e.g. the Fleet page table) rather than pixel-verified — disclosed here rather than
claimed as tested.

## Known limitations

- `/intelligence` (the "Intelligence (raw)" secondary-nav page, deliberately kept as a
  technical/system view) still has its own local `replaceAll("_", " ")` and duplicated
  tone functions rather than importing `lib/terminology.ts` — left as-is since the page
  is explicitly the raw/technical view, not a primary product page.
- The frontend permission mirror (`lib/permissions.ts`) can drift from the backend's
  `app/auth/permissions.py` if one is edited without the other (ADR-160) — there is no
  automated check for this today.
- No automated visual-regression or accessibility-audit tooling is wired into CI;
  responsiveness/accessibility verification for the Organization Command Center's
  narrow-viewport behavior specifically was a code-level review, not a pixel-verified
  one, per the manual-verification note above.
- Machine Detail has no energy/carbon evidence surface yet — Lubrication Efficiency
  Intelligence (ADR-176) remains backend-only; the Organization Command Center's energy/
  carbon sections link out to Data Quality where relevant, never to a
  Machine-Detail energy tab that doesn't exist.
