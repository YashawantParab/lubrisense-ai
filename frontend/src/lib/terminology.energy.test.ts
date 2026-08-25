import { describe, expect, it } from "vitest";

import {
  attributionLevelTone,
  carbonEstimateStatusTone,
  comparabilityStatusTone,
  energyAssessmentStatusTone,
  energyOutcomeStatusTone,
  lubricationAssociationStatusTone,
} from "@/lib/terminology";

describe("energyAssessmentStatusTone", () => {
  it("marks within-expected-range as ok and elevated demand as warn", () => {
    expect(energyAssessmentStatusTone("WITHIN_EXPECTED_RANGE")).toBe("ok");
    expect(energyAssessmentStatusTone("ELEVATED_ENERGY_DEMAND")).toBe("warn");
  });
});

describe("attributionLevelTone", () => {
  it("gives every level a distinct, monotonically-escalating tone", () => {
    expect(attributionLevelTone("NO_EVIDENCE")).toBe("neutral");
    expect(attributionLevelTone("POSSIBLE")).toBe("warn");
    expect(attributionLevelTone("MODERATE")).toBe("warn");
    expect(attributionLevelTone("STRONG")).toBe("error");
  });
});

describe("comparabilityStatusTone", () => {
  it("marks comparable as ok and not-comparable as error", () => {
    expect(comparabilityStatusTone("COMPARABLE")).toBe("ok");
    expect(comparabilityStatusTone("NOT_COMPARABLE")).toBe("error");
  });
});

describe("energyOutcomeStatusTone", () => {
  it("treats a qualified and probable recovery as ok, deterioration as error", () => {
    expect(energyOutcomeStatusTone("QUALIFIED_RECOVERY")).toBe("ok");
    expect(energyOutcomeStatusTone("PROBABLE_RECOVERY")).toBe("ok");
    expect(energyOutcomeStatusTone("DETERIORATED")).toBe("error");
  });
});

describe("lubricationAssociationStatusTone", () => {
  it("does not distinguish tone between qualified and lubrication-associated recovery (both real recoveries)", () => {
    expect(lubricationAssociationStatusTone("QUALIFIED_ENERGY_RECOVERY")).toBe("ok");
    expect(lubricationAssociationStatusTone("LUBRICATION_ASSOCIATED_RECOVERY")).toBe("ok");
  });
});

describe("carbonEstimateStatusTone", () => {
  it("marks estimate-available as ok and not-eligible as neutral, never error", () => {
    expect(carbonEstimateStatusTone("ESTIMATE_AVAILABLE")).toBe("ok");
    expect(carbonEstimateStatusTone("NOT_ELIGIBLE")).toBe("neutral");
  });
});
