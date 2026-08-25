import { describe, expect, it } from "vitest";

import {
  actionReadinessStateTone,
  dataTrustCategoryTone,
  energyBucketTone,
  maintenanceOutcomeBucketTone,
  portfolioOutcomeTone,
  portfolioPriorityTone,
} from "@/lib/terminology";

describe("portfolioPriorityTone", () => {
  it("marks critical attention as error and monitor as ok", () => {
    expect(portfolioPriorityTone("CRITICAL_ATTENTION")).toBe("error");
    expect(portfolioPriorityTone("MONITOR")).toBe("ok");
  });

  it("marks data-limited as neutral, never error (it is not a severity claim)", () => {
    expect(portfolioPriorityTone("DATA_LIMITED")).toBe("neutral");
  });
});

describe("actionReadinessStateTone", () => {
  it("marks assessment-blocked as error and monitoring-only as ok", () => {
    expect(actionReadinessStateTone("ASSESSMENT_BLOCKED")).toBe("error");
    expect(actionReadinessStateTone("MONITORING_ONLY")).toBe("ok");
  });
});

describe("energyBucketTone", () => {
  it("distinguishes an active opportunity (warn) from a qualified recovery (ok)", () => {
    expect(energyBucketTone("ACTIVE_ELEVATED_ENERGY")).toBe("warn");
    expect(energyBucketTone("ATTRIBUTION_SUPPORTED_OPPORTUNITY")).toBe("warn");
    expect(energyBucketTone("QUALIFIED_ENERGY_RECOVERY")).toBe("ok");
  });

  it("marks a deteriorated outcome as error, never folded into inconclusive", () => {
    expect(energyBucketTone("OUTCOME_DETERIORATED")).toBe("error");
    expect(energyBucketTone("OUTCOME_DETERIORATED")).not.toBe(
      energyBucketTone("INCONCLUSIVE_OUTCOME"),
    );
  });
});

describe("maintenanceOutcomeBucketTone", () => {
  it("never treats plain completion as automatic success", () => {
    expect(maintenanceOutcomeBucketTone("COMPLETED_QUALIFIED_RECOVERY")).toBe("ok");
    expect(maintenanceOutcomeBucketTone("COMPLETED_DETERIORATED")).toBe("error");
    expect(maintenanceOutcomeBucketTone("COMPLETED_INCONCLUSIVE")).toBe("neutral");
  });
});

describe("dataTrustCategoryTone", () => {
  it("marks both blocked categories as error", () => {
    expect(dataTrustCategoryTone("ASSESSMENT_BLOCKED")).toBe("error");
    expect(dataTrustCategoryTone("ACTION_BLOCKED")).toBe("error");
  });

  it("marks decision-evidence-trusted as ok", () => {
    expect(dataTrustCategoryTone("DECISION_EVIDENCE_TRUSTED")).toBe("ok");
  });
});

describe("portfolioOutcomeTone", () => {
  it("gives every known outcome type a defined tone", () => {
    const types = [
      "CONDITION_RESOLVED",
      "CONDITION_IMPROVING",
      "MAINTENANCE_COMPLETED",
      "QUALIFIED_ENERGY_RECOVERY",
      "CARBON_ESTIMATE_PRODUCED",
    ];
    for (const type of types) {
      expect(["ok", "warn", "error", "info", "neutral"]).toContain(portfolioOutcomeTone(type));
    }
  });
});
