# Commissioning (Phase 30)

## Purpose

A guided **demo** onboarding workflow for adding a new machine to the platform — not a
real industrial installer, no physical device discovery, no protocol handshake with
real hardware. Every step creates real, persisted records; nothing here contacts a real
sensor, gateway, or controller. See CLAUDE.md's "Industrial Adoption Boundary" for why
this distinction matters.

## Domain model

`app/commissioning/` owns:

- **`CommissioningSession`** — one per in-progress or completed onboarding, tenant-
  scoped, tied to exactly one `Machine` (created together with the session). Tracks
  `status`, `capability_level`, `validation_issues` (JSONB), `steps_completed` (JSONB),
  and `completed_at`.
- **`CommissioningStatus`** — `DRAFT → CONFIGURING → VALIDATING → READY/FAILED →
  COMPLETED`.
- **`CapabilityLevel`** — `NONE / BASIC_MONITORING / DELIVERY_INTELLIGENCE /
  BEARING_INTELLIGENCE / FULL_INTELLIGENCE`, computed from the sensor types actually
  registered — never hand-set, never inferred from "commissioning ran" alone.

## The workflow

1. **Start session** (`POST /commissioning/sessions`) — creates the `Machine` (status
   `COMMISSIONING`) and the `CommissioningSession` together, under a chosen production
   line, with a name/asset code/machine type.
2. **Add sensor(s)** (`POST .../sensors`, repeatable) — sensor type, unit, code, name.
   Each call also captures a device-configuration snapshot (Phase 31 integration — see
   `docs/DEVICE_CONFIGURATION.md`).
3. **Assign gateway** (`POST .../gateway`, optional) — selects from `GET /gateways`
   (filterable by site), also captures a configuration snapshot.
4. **Validate** (`POST .../validate`) — computes `capability_level` and a structured
   list of issues (see below), sets `READY` or `FAILED`.
5. **Complete** (`POST .../complete`) — requires `READY`; sets `Machine.status =
   MONITORED`, `CommissioningSession.status = COMPLETED`, records a
   `COMMISSIONING_COMPLETED` audit event (Phase 25 integration).

The frontend wizard (`/configuration/commission`) walks through exactly these five
steps, with `?sessionId=` resume support so an in-progress session survives a page
reload or a shared link.

## Minimum-viable-instrumentation policy (`app/commissioning/policy.py`)

`compute_capability_level(sensor_types)`:

| Sensor types present | Capability level |
|---|---|
| `PRESSURE` **and** one of `{RESERVOIR_LEVEL, PUMP_CURRENT, FLOW}` **and** one of `{VIBRATION_RMS, VIBRATION_PEAK, BEARING_TEMPERATURE}` | `FULL_INTELLIGENCE` |
| `PRESSURE` **and** one of `{RESERVOIR_LEVEL, PUMP_CURRENT, FLOW}` only | `DELIVERY_INTELLIGENCE` |
| One of `{VIBRATION_RMS, VIBRATION_PEAK, BEARING_TEMPERATURE}` only | `BEARING_INTELLIGENCE` |
| Any sensor, but none of the above combinations | `BASIC_MONITORING` |
| No sensors at all | `NONE` |

**FLOW is deliberately never required.** The flagship demo topology has no FLOW
sensor — `PRESSURE` plus *any one* of `RESERVOIR_LEVEL`/`PUMP_CURRENT`/`FLOW` satisfies
the delivery-intelligence secondary-indicator requirement (see ADR-161). This is
covered directly by
`tests/commissioning/test_commissioning_service.py::
test_flagship_topology_without_flow_reaches_full_intelligence` and was re-verified live
through the commissioning wizard.

Expected units per sensor type (`EXPECTED_UNITS`) are checked by `is_unit_expected()`
— a mismatch is always a `WARNING`, never blocking; this is a demo-data-quality nudge,
not an enforced calibration standard.

## Validation: what actually blocks completion

`CommissioningService.validate()` treats exactly **one** condition as blocking: zero
sensors mapped to the machine. Everything else is a non-blocking `WARNING`, visible in
the wizard's validation-result panel:

- `UNEXPECTED_UNIT` — a mapped sensor's unit doesn't match the expected unit for its
  type
- `NO_GATEWAY_ASSIGNED` — no gateway selected
- `GATEWAY_NOT_ACTIVE` — an assigned gateway's status isn't `ACTIVE`
- `NO_TELEMETRY_YET` — always present for a freshly commissioned demo asset, since
  telemetry only starts flowing once the edge/simulator pipeline is pointed at it
  *after* commissioning — this is expected, not a defect

See ADR-162 for why only "no instrumentation at all" blocks: a stricter policy would
make it impossible to ever complete commissioning for a genuinely new demo machine.

## What "capability profile" promises — and doesn't

`CapabilityLevel` reflects only the sensor types actually registered to the machine at
validation time. It is never promoted based on commissioning status alone, and it is
never a guarantee that telemetry is currently flowing — `NO_TELEMETRY_YET` can coexist
with `READY`/`COMPLETED` and any capability level. The machine detail page's Machine
Intelligence panel always shows the real, current evidence counts (rule findings, ML
results, state estimates) independent of what capability level commissioning assigned.

## Live demo result

Two demo machines were commissioned end-to-end through the real UI against the real
backend during this sprint's verification:

- **"Retest Wizard Motor"** — `PRESSURE` + `RESERVOIR_LEVEL` + `VIBRATION_RMS` sensors,
  no FLOW sensor, gateway assigned. Validation returned `READY` /
  `FULL_INTELLIGENCE` with only the expected `NO_TELEMETRY_YET` warning. Completed
  successfully; machine transitioned to `MONITORED`.
- **"Demo Wizard Motor"** — `PRESSURE` + `VIBRATION_RMS` only (no secondary delivery
  indicator). Validation correctly returned only `BEARING_INTELLIGENCE` — confirming
  the policy responds to actual instrumentation, not to commissioning having merely
  run.

A real backend bug was found and fixed during this live verification: both
`assign_gateway()` and `complete()` originally 503'd on a `MissingGreenlet` error
because they returned a mutated `CommissioningSession` for serialization without first
refreshing its server-computed `updated_at` after an internal audit-triggered flush.
See ADR-165 for the full root cause and fix.

## Explicitly not implemented

No real physical device discovery, no protocol handshake, no contact with real
hardware anywhere in this package — matching CLAUDE.md's demo/reference-implementation
boundary exactly.
