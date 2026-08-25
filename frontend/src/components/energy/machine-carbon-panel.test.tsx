import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MachineCarbonPanel } from "@/components/energy/machine-carbon-panel";
import type { CarbonImpactEstimate } from "@/lib/api/energy-types";

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
});
