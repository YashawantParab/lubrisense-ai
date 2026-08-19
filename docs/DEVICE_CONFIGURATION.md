# Device / Firmware Configuration Management (Phase 31)

## Purpose

Represent configuration and firmware **provenance** for gateways, controllers, and
sensors — who changed what, when, and why — as a governance/audit surface. This is
**not** a real OTA (over-the-air) update system. Nothing in this package ever sends a
command to a device or to any machinery; see the "No-OTA safety boundary" section below
and ADR-163.

## Domain model

`app/device_management/`:

- **`ConfigurationSnapshot`** — one point-in-time record of a device's configuration
  (`device_type`, `device_id`, `firmware_version`, `config` JSONB — sampling interval,
  unit, sensor mapping, controller/gateway config metadata; **never secrets**,
  `compatibility_status`). Exactly one snapshot per device has `is_current = True` at
  any time; capturing a new snapshot for the same device flips the prior one's
  `is_current` to `False` rather than deleting it — full history is retained.
- **`ConfigurationChange`** — append-only. References the old and new snapshot, the
  actor, a reason, a source, a timestamp, and a `baseline_review_required` flag. No
  update or delete method exists anywhere in this package for this table, matching the
  same append-only discipline Phase 25's `AuditEvent` already established.
- **`DeviceType`** — `GATEWAY / CONTROLLER / SENSOR`.
- **`CompatibilityStatus`** — `SUPPORTED / SUPPORTED_WITH_LIMITATIONS / UNKNOWN /
  INCOMPATIBLE`.

## Compatibility model

`classify_compatibility(firmware_version)` — a simple, generic, demo-only convention:

| Firmware major version | Compatibility |
|---|---|
| `>= 2` | `SUPPORTED` |
| `== 1` | `SUPPORTED_WITH_LIMITATIONS` |
| `< 1`, non-numeric, or missing | `INCOMPATIBLE` / `UNKNOWN` |

This is deliberately a generic convention, not an invented real manufacturer
specification — CLAUDE.md requires synthetic ranges/specs to be labelled as demo
assumptions, never presented as proprietary industrial data. A gateway with firmware
`0.9.0-demo` (a synthetic version used for the demo gateway fleet) correctly classifies
as `Incompatible` under this rule, and is displayed as such on the machine detail
page's Device/Configuration table — the compatibility badge is not softened or hidden
because the device is "just a demo."

## When snapshots are captured

`DeviceConfigurationService.capture_snapshot()` is called directly from
`CommissioningService.add_sensor()` and `.assign_gateway()` — commissioning is the
natural point of first configuration for a device, so the two packages are tightly
integrated by design rather than requiring a separate manual "register configuration"
step. Every device added through the commissioning wizard automatically gets its first
`ConfigurationSnapshot` and its first `ConfigurationChange` entry.

Machines commissioned before this sprint (pre-Phase-30 demo data) simply have no
snapshot history — the machine detail page shows an honest
`"No device configuration recorded yet"` empty state for them, not a fabricated one.

## Baseline impact

`_is_significant_change()` computes `baseline_review_required` on every
`ConfigurationChange`:

- `False` if no prior snapshot existed for the device (nothing to invalidate — this is
  the device's first configuration).
- `True` if the firmware version differs from the prior snapshot, **or** any of
  `sampling_interval_seconds` / `unit` / `calibration_offset` changed in `config`.

This is a **flag only** — a `baseline_review_required = True` change never
automatically expires, deletes, or recomputes any `BaselineProfile`. A human
(reliability engineer) decides whether an existing baseline is still valid after
reviewing the actual change; the platform's own baseline history is never destroyed as
a side effect of a configuration change (see ADR-164). The flag is surfaced as an amber
callout in the machine detail page's expandable change-history list.

## Machine-level UI

The machine detail page's **Device / Configuration** section (below Telemetry, above
the collapsible Asset details) shows:

- A table of current snapshots — device type, firmware version, compatibility badge,
  time captured — one row per device (gateway/controller/sensors) attached to the
  machine.
- An expandable "Show change history" list — every `ConfigurationChange` for the
  machine's devices, most recent first, with actor, reason, source, and the
  baseline-review-required callout when applicable.

Verified live: the "Retest Wizard Motor" demo machine commissioned in Phase 30 shows 4
device rows (1 gateway + 3 sensors, matching what was actually registered) with correct
compatibility badges, and a 4-entry change history correctly attributed to the demo
admin actor with real reason strings and relative timestamps.

## No-OTA safety boundary

Every route in `app/api/v1/device_management.py` is read-only. The only writer,
`capture_snapshot()`, is called exclusively from commissioning's own sensor/gateway
registration steps — there is no route or service method anywhere in this package that
accepts a caller-supplied "push this configuration to the device" request, and no code
path sends any command to a device or to machinery. Verified by inspection (no
`@router.post`/`@router.put`/`@router.patch` exists in `app/api/v1/device_management.py`
at all).

## Explicitly not implemented

No real firmware artifact storage, no staged rollout, no rollback mechanism, no
OTA/remote-flashing capability — this package only ever records provenance/history for
governance visibility, exactly as CLAUDE.md's Workflow Intelligence boundary requires
("Not allowed: operate machinery... override PLC... alter safety settings").
