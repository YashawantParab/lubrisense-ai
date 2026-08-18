/** Maps backend status/criticality enum values to a StatusPill tone. Purely
 * presentational — the enum values themselves are the source of truth from the API. */

const ERROR_VALUES = new Set(["CRITICAL", "OFFLINE", "FAULTY", "SUSPENDED", "RETIRED"]);
const WARN_VALUES = new Set(["HIGH", "MAINTENANCE", "DEGRADED", "COMMISSIONING", "PILOT"]);
const NEUTRAL_VALUES = new Set([
  "REGISTERED",
  "INACTIVE",
  "DECOMMISSIONED",
  "PLANNED",
  "UNKNOWN",
  "PROSPECT",
]);

export function toneForStatus(value: string): "ok" | "warn" | "error" | "neutral" {
  if (ERROR_VALUES.has(value)) return "error";
  if (WARN_VALUES.has(value)) return "warn";
  if (NEUTRAL_VALUES.has(value)) return "neutral";
  return "ok";
}
