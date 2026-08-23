/**
 * Product-presentation equipment identity — the single place that decides what a machine
 * is *called* in primary customer-facing UI, separate from the coarse internal
 * `machine_type` enum (six fixed categories — CLAUDE.md's asset hierarchy) that backend
 * logic, the simulator, and historical tests still key off. Only the curated showcase
 * fleet carries a specific `equipment_class`/`area` (seeded into `Machine.metadata_` —
 * `backend/scripts/seed_demo_data.py`'s `CURATED_MACHINE_NAMES`); every other machine
 * falls back to the humanized internal enum, so nothing regresses for the rest of the
 * fleet. `machine_type` itself is never hidden — it still renders as-is in Technical
 * Provenance / engineering surfaces — this only changes what *primary* UI leads with.
 */

import { humanize } from "@/lib/terminology";

/** Reads a string-typed key out of a loosely-typed metadata bag (e.g. `MachineResponse.
 * metadata`), returning null for anything absent or non-string rather than throwing. */
export function stringMeta(
  metadata: Record<string, unknown> | null | undefined,
  key: string,
): string | null {
  const value = metadata?.[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

/** The equipment type to lead with in primary UI: the specific curated class (e.g. "Ball
 * Mill") when set, otherwise the humanized coarse `machine_type` enum. */
export function equipmentTypeFor(
  machineType: string,
  equipmentClass: string | null | undefined,
): string {
  return equipmentClass || humanize(machineType);
}

/**
 * The lubricated component/circuit named in a curated machine's own display name (every
 * curated name is seeded as `"{Equipment} {TAG} – {Component}"`) — derived from the one
 * canonical `name` string rather than a second field that could drift out of sync with
 * it. Returns null for a name with no em-dash (every non-curated machine), so callers can
 * fall back to a generic, non-contextual message.
 */
export function componentFromName(name: string): string | null {
  const parts = name.split(" – ");
  return parts.length > 1 ? parts[1].trim() : null;
}

/** The equipment + tag portion of a curated machine's display name, without the
 * lubricated-component suffix (e.g. "Ball Mill BM-301" from "Ball Mill BM-301 – Pinion
 * Bearing Lubrication Circuit") — for a two-line header. Falls back to the whole name
 * when there's no component suffix to split off. */
export function equipmentNameFromName(name: string): string {
  return name.split(" – ")[0].trim();
}
