/**
 * Carbon-calculation transparency helpers (Enterprise Product Rebuild Pass 2 §6/§7) —
 * extracts the emission-factor provenance the backend already writes into
 * `CarbonImpactEstimate.provenance` (`app/energy/services/carbon_service.py`:
 * source_name/source_reference/jurisdiction/effective_from/effective_to/provenance) so
 * the "How this is calculated" panel can show real factor source and effective period,
 * never a fabricated one. `provenance` is a loosely-typed JSON bag at the wire boundary —
 * every read here is defensive (typeof-checked, never assumed present).
 */

export interface FactorProvenance {
  sourceName: string | null;
  sourceReference: string | null;
  jurisdiction: string | null;
  effectiveFrom: string | null;
  effectiveTo: string | null;
  provenanceLabel: string | null;
}

function stringField(bag: Record<string, unknown>, key: string): string | null {
  const value = bag[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

export function extractFactorProvenance(
  provenance: Record<string, unknown> | null | undefined,
): FactorProvenance {
  const bag = provenance ?? {};
  return {
    sourceName: stringField(bag, "source_name"),
    sourceReference: stringField(bag, "source_reference"),
    jurisdiction: stringField(bag, "jurisdiction"),
    effectiveFrom: stringField(bag, "effective_from"),
    effectiveTo: stringField(bag, "effective_to"),
    provenanceLabel: stringField(bag, "provenance"),
  };
}

export function formatEffectivePeriod(factor: FactorProvenance): string {
  if (!factor.effectiveFrom) return "Not available";
  const from = new Date(factor.effectiveFrom).toLocaleDateString();
  const to = factor.effectiveTo ? new Date(factor.effectiveTo).toLocaleDateString() : "present";
  return `${from} – ${to}`;
}

/** The dynamic worked calculation for the "How this is calculated" panel — real numbers
 * from this estimate, never hardcoded seeded values. Returns null when either operand is
 * unavailable (nothing to multiply). */
export function calculationLine(
  qualifiedAvoidedEnergyKwh: number | null,
  emissionFactorValue: number | null,
  emissionFactorUnit: string | null,
): string | null {
  if (qualifiedAvoidedEnergyKwh === null || emissionFactorValue === null) return null;
  const product = qualifiedAvoidedEnergyKwh * emissionFactorValue;
  return `${qualifiedAvoidedEnergyKwh.toFixed(2)} kWh × ${emissionFactorValue} ${emissionFactorUnit ?? ""} = ${product.toFixed(2)} kg CO2e`;
}
