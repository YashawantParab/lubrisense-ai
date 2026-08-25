import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EnergyOutcomeJourney } from "@/components/energy/energy-outcome-journey";
import type { CarbonImpactEstimate, EnergyOutcomeVerification } from "@/lib/api/energy-types";

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

describe("EnergyOutcomeJourney", () => {
  it("reaches all three stages for a qualified recovery with a carbon estimate", () => {
    const carbon: CarbonImpactEstimate = {
      id: "c-1",
      tenant_id: "t-1",
      site_id: "s-1",
      machine_id: "m-1",
      energy_outcome_verification_id: "o-1",
      emission_factor_id: "f-1",
      observed_period_start: null,
      observed_period_end: null,
      qualified_avoided_energy_kwh: 1.1,
      emission_factor_value: 0.4,
      emission_factor_unit: "kg_co2e_per_kwh",
      method: "LOCATION_BASED",
      estimated_co2e_kg: 0.43,
      estimate_status: "ESTIMATE_AVAILABLE",
      limitations: [],
      provenance: {},
      policy_version: "1",
      created_at: new Date().toISOString(),
    };
    render(<EnergyOutcomeJourney outcome={outcome()} carbon={carbon} />);
    expect(screen.getByText("0.43 kg CO2e")).toBeInTheDocument();
    expect(screen.getByText("~1.1 kWh qualified")).toBeInTheDocument();
  });

  it("does not reach energy recovery or carbon stages for a non-qualified outcome", () => {
    render(
      <EnergyOutcomeJourney
        outcome={outcome({ energy_outcome_status: "INSUFFICIENT_DATA" })}
        carbon={null}
      />,
    );
    expect(screen.getByText("Not qualified")).toBeInTheDocument();
    expect(screen.getByText("Not eligible")).toBeInTheDocument();
  });
});
