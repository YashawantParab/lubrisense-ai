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

Primary navigation (the product):

`Overview → Fleet → Incidents → Maintenance → Knowledge → Assistant → Metrics`

Secondary "System" navigation (technical/developer inspection, still fully functional,
visually demoted rather than removed — see ADR-158):

`Configuration → Audit → Asset Hierarchy → Sensor Inventory → Data Quality → Baselines
→ Rule Findings → Features → ML → State Estimation → Intelligence (raw) → System Status`

`/` redirects to `/overview`. The application shell (`components/app-shell.tsx`) is a
fixed sidebar (mobile: hamburger overlay) showing product identity, a live
`SystemStatusDot` (backend readiness), and a demo identity/role switcher in the top
bar.

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

## Known limitations

- `/intelligence` (the "Intelligence (raw)" secondary-nav page, deliberately kept as a
  technical/system view) still has its own local `replaceAll("_", " ")` and duplicated
  tone functions rather than importing `lib/terminology.ts` — left as-is since the page
  is explicitly the raw/technical view, not a primary product page.
- The frontend permission mirror (`lib/permissions.ts`) can drift from the backend's
  `app/auth/permissions.py` if one is edited without the other (ADR-160) — there is no
  automated check for this today.
- No automated visual-regression or accessibility-audit tooling is wired into CI; all
  responsiveness/accessibility verification this sprint was manual.
