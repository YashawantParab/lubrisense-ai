import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MachineCarbonPanel } from "@/components/energy/machine-carbon-panel";
import type { CarbonImpactEstimate, EnergyOutcomeVerification } from "@/lib/api/energy-types";

function estimate(overrides: Partial<CarbonImpactEstimate> = {}): CarbonImpactEstimate {
  return {
    id: "c-1",
    tenant_id: "t-1",
    site_id: "s-1",
    machine_id: "m-1",
    energy_outcome_verification_id: "o-1",
    emission_factor_id: "f-1",
    observed_period_start: "2026-08-25T00:00:00Z",
    observed_period_end: "2026-08-25T00:00:00Z",
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
    ...overrides,
  };
}

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

describe("MachineCarbonPanel", () => {
  it("shows the real figure when an estimate is available", () => {
    render(<MachineCarbonPanel estimate={estimate()} />);
    expect(screen.getByText("0.43 kg CO2e")).toBeInTheDocument();
  });

  it("never renders '0 kg' when the emission factor is not configured — explains why instead", () => {
    render(
      <MachineCarbonPanel
        estimate={estimate({
          estimate_status: "FACTOR_NOT_CONFIGURED",
          estimated_co2e_kg: null,
          emission_factor_value: null,
        })}
      />,
    );
    expect(screen.queryByText(/0.00 kg CO2e/)).not.toBeInTheDocument();
    expect(screen.getByText(/not configured/)).toBeInTheDocument();
  });

  it("never claims carbon saved, certified reduction, or net-zero", () => {
    render(<MachineCarbonPanel estimate={estimate()} />);
    expect(screen.queryByText(/carbon saved/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/certified reduction achieved/i)).not.toBeInTheDocument();
    expect(
      screen.getByText(/Never a claim of certified reduction or net-zero contribution/),
    ).toBeInTheDocument();
  });

  it("'How this is calculated' shows the real worked formula, never a hardcoded figure", () => {
    render(<MachineCarbonPanel estimate={estimate()} />);
    expect(
      screen.getByText(
        "Estimated CO2e = Qualified observed avoided energy × Applicable configured electricity emission factor",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("1.10 kWh × 0.4 kg_co2e_per_kwh = 0.44 kg CO2e")).toBeInTheDocument();
  });

  it("shows real factor source/effective-period provenance from the estimate, not a placeholder", () => {
    render(
      <MachineCarbonPanel
        estimate={estimate({
          provenance: {
            source_name: "Illustrative demonstration factor (not an audited grid dataset)",
            source_reference: null,
            jurisdiction: null,
            effective_from: "2026-08-25T00:00:00Z",
            effective_to: null,
            provenance: "DEMO_ESTIMATE",
          },
        })}
      />,
    );
    expect(
      screen.getByText("Illustrative demonstration factor (not an audited grid dataset)"),
    ).toBeInTheDocument();
    expect(screen.getByText(/present/)).toBeInTheDocument();
    expect(screen.getByText("DEMO ESTIMATE")).toBeInTheDocument();
  });

  it("traces to the qualifying energy outcome — comparability, confidence, and source case link", () => {
    render(<MachineCarbonPanel estimate={estimate()} outcome={outcome()} />);
    expect(screen.getByText("Comparable")).toBeInTheDocument();
    expect(screen.getByText("High")).toBeInTheDocument();
    const link = screen.getByText("View qualified energy outcome →");
    expect(link.closest("a")).toHaveAttribute("href", "/maintenance/c-1");
  });

  it("omits the outcome-traceability fields when no outcome is passed, rather than fabricating them", () => {
    render(<MachineCarbonPanel estimate={estimate()} />);
    expect(screen.queryByText("View qualified energy outcome →")).not.toBeInTheDocument();
  });
});
