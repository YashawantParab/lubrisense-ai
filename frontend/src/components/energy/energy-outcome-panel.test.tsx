import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EnergyOutcomePanel } from "@/components/energy/energy-outcome-panel";
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
    pre_mean_actual_power_kw: 29.8,
    pre_mean_expected_power_kw: 27.6,
    pre_mean_residual_kw: 2.23,
    pre_mean_residual_pct: 7.4,
    post_mean_actual_power_kw: 29.98,
    post_mean_expected_power_kw: 30.06,
    post_mean_residual_kw: -0.08,
    post_mean_residual_pct: -0.3,
    residual_change_kw: 2.31,
    residual_change_pct: 7.7,
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

describe("EnergyOutcomePanel", () => {
  it("a BE-201-shaped qualified recovery shows the observed kWh with correct (non-doubled) percentages", () => {
    render(<EnergyOutcomePanel outcome={outcome()} />);
    expect(screen.getByText("2.23 kW (+7.4%)")).toBeInTheDocument();
    expect(screen.getByText("-0.08 kW (-0.3%)")).toBeInTheDocument();
    expect(screen.getByText("~1.1 kWh")).toBeInTheDocument();
    expect(screen.getByText("No Evidence")).toBeInTheDocument();
  });

  it("never annualizes or projects the avoided-energy figure forward", () => {
    render(<EnergyOutcomePanel outcome={outcome()} />);
    expect(screen.getByText(/never annualized or projected forward/)).toBeInTheDocument();
  });

  it("shows a non-qualified outcome just as plainly, without a fabricated kWh figure", () => {
    render(
      <EnergyOutcomePanel
        outcome={outcome({
          energy_outcome_status: "INSUFFICIENT_DATA",
          estimated_avoided_energy_kwh: null,
          lubrication_association_status: "NOT_APPLICABLE",
          pre_mean_residual_kw: null,
          pre_mean_residual_pct: null,
          post_mean_residual_kw: null,
          post_mean_residual_pct: null,
          residual_change_kw: null,
          residual_change_pct: null,
        })}
      />,
    );
    expect(screen.queryByText(/kWh/)).not.toBeInTheDocument();
    expect(
      screen.getByText("No energy-recovery claim applies to this outcome."),
    ).toBeInTheDocument();
  });
});
