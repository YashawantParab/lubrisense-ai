import { describe, expect, it } from "vitest";

import { associationWording } from "@/lib/energy-outcome-wording";
import type { EnergyOutcomeVerification } from "@/lib/api/energy-types";

function outcome(overrides: Partial<EnergyOutcomeVerification> = {}): EnergyOutcomeVerification {
  return {
    id: "o-1",
    tenant_id: "t-1",
    machine_id: "m-1",
    maintenance_case_id: "c-1",
    incident_id: null,
    intervention_timestamp: new Date().toISOString(),
    pre_window_start: null,
    pre_window_end: null,
    post_window_start: null,
    post_window_end: null,
    pre_mean_actual_power_kw: null,
    pre_mean_expected_power_kw: null,
    pre_mean_residual_kw: null,
    pre_mean_residual_pct: null,
    post_mean_actual_power_kw: null,
    post_mean_expected_power_kw: null,
    post_mean_residual_kw: null,
    post_mean_residual_pct: null,
    residual_change_kw: null,
    residual_change_pct: null,
    comparability_status: "COMPARABLE",
    comparison_confidence: "HIGH",
    energy_outcome_status: "QUALIFIED_RECOVERY",
    estimated_avoided_energy_kwh: 1.1,
    energy_estimate_status: "ESTIMATED",
    pre_attribution_id: null,
    pre_attribution_level: "NO_EVIDENCE",
    condition_outcome_status: null,
    maintenance_relevant: true,
    lubrication_association_status: "QUALIFIED_ENERGY_RECOVERY",
    supporting_evidence: [],
    contradicting_evidence: [],
    limiting_factors: [],
    alternative_explanations: [],
    provenance: {},
    policy_version: "1",
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

describe("associationWording", () => {
  it("a BE-201-shaped case (qualified recovery, NO_EVIDENCE pre-attribution) never claims a lubrication-associated recovery", () => {
    const wording = associationWording(
      outcome({ lubrication_association_status: "QUALIFIED_ENERGY_RECOVERY" }),
    );
    expect(wording).toBe(
      "Energy performance improved following intervention under comparable operation.",
    );
    expect(wording).not.toMatch(/lubrication/i);
    expect(wording).not.toMatch(/saved/i);
  });

  it("only claims a lubrication-associated recovery when the status says so", () => {
    const wording = associationWording(
      outcome({ lubrication_association_status: "LUBRICATION_ASSOCIATED_RECOVERY" }),
    );
    expect(wording).toMatch(/lubrication-related contribution/);
  });

  it("never overclaims an observed-but-not-qualified change", () => {
    const wording = associationWording(
      outcome({ lubrication_association_status: "OBSERVED_ENERGY_CHANGE" }),
    );
    expect(wording).toMatch(/does not yet meet the bar/);
  });

  it("says nothing applies when not applicable", () => {
    expect(associationWording(outcome({ lubrication_association_status: "NOT_APPLICABLE" }))).toBe(
      "No energy-recovery claim applies to this outcome.",
    );
  });
});
