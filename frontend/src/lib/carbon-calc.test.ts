import { describe, expect, it } from "vitest";

import { calculationLine, extractFactorProvenance, formatEffectivePeriod } from "@/lib/carbon-calc";

describe("extractFactorProvenance", () => {
  it("reads real string fields defensively, never assuming presence", () => {
    const result = extractFactorProvenance({
      source_name: "Illustrative demonstration factor",
      source_reference: "ref-1",
      jurisdiction: "US",
      effective_from: "2026-08-25T00:00:00Z",
      effective_to: null,
      provenance: "DEMO_ESTIMATE",
    });
    expect(result.sourceName).toBe("Illustrative demonstration factor");
    expect(result.effectiveTo).toBeNull();
  });

  it("returns all-null fields for missing/empty provenance rather than throwing", () => {
    expect(extractFactorProvenance(null)).toEqual({
      sourceName: null,
      sourceReference: null,
      jurisdiction: null,
      effectiveFrom: null,
      effectiveTo: null,
      provenanceLabel: null,
    });
    expect(extractFactorProvenance({})).toEqual({
      sourceName: null,
      sourceReference: null,
      jurisdiction: null,
      effectiveFrom: null,
      effectiveTo: null,
      provenanceLabel: null,
    });
  });

  it("ignores a non-string value under a known key rather than surfacing garbage", () => {
    const result = extractFactorProvenance({ source_name: 42 });
    expect(result.sourceName).toBeNull();
  });
});

describe("formatEffectivePeriod", () => {
  it("shows 'present' for an open-ended (still-active) factor", () => {
    const label = formatEffectivePeriod({
      sourceName: null,
      sourceReference: null,
      jurisdiction: null,
      effectiveFrom: "2026-08-25T00:00:00Z",
      effectiveTo: null,
      provenanceLabel: null,
    });
    expect(label).toMatch(/present$/);
  });

  it("returns 'Not available' when the factor's own effective_from is unknown", () => {
    expect(
      formatEffectivePeriod({
        sourceName: null,
        sourceReference: null,
        jurisdiction: null,
        effectiveFrom: null,
        effectiveTo: null,
        provenanceLabel: null,
      }),
    ).toBe("Not available");
  });
});

describe("calculationLine", () => {
  it("computes the real product from the estimate's own operands — never a hardcoded number", () => {
    expect(calculationLine(1.1, 0.4, "kg_co2e_per_kwh")).toBe(
      "1.10 kWh × 0.4 kg_co2e_per_kwh = 0.44 kg CO2e",
    );
  });

  it("returns null (not a fabricated 0) when either operand is unavailable", () => {
    expect(calculationLine(null, 0.4, "kg_co2e_per_kwh")).toBeNull();
    expect(calculationLine(1.1, null, "kg_co2e_per_kwh")).toBeNull();
  });
});
