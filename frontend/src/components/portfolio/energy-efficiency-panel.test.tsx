import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EnergyEfficiencyPanel } from "@/components/portfolio/energy-efficiency-panel";

describe("EnergyEfficiencyPanel", () => {
  it("labels active opportunities and qualified outcomes under separate headings, never 'Savings'", () => {
    render(
      <EnergyEfficiencyPanel
        activeOpportunities={1}
        attributionSupportedOpportunities={1}
        qualifiedRecoveryCount={1}
        qualifiedAvoidedEnergyKwhTotal={1.1}
      />,
    );
    expect(screen.getByText("Active opportunities")).toBeInTheDocument();
    expect(screen.getByText("Qualified outcomes")).toBeInTheDocument();
    expect(screen.queryByText(/^Savings$/)).not.toBeInTheDocument();
  });

  it("an IDF-01-shaped opportunity (active, no qualified recovery yet) never claims a kWh figure", () => {
    render(
      <EnergyEfficiencyPanel
        activeOpportunities={1}
        attributionSupportedOpportunities={1}
        qualifiedRecoveryCount={0}
        qualifiedAvoidedEnergyKwhTotal={0}
      />,
    );
    expect(
      screen.getByText(/No comparability-gated, residual-verified energy recovery/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/kWh/)).not.toBeInTheDocument();
  });

  it("a BE-201-shaped qualified recovery states the observed kWh and explicitly disclaims annualizing it", () => {
    render(
      <EnergyEfficiencyPanel
        activeOpportunities={0}
        qualifiedRecoveryCount={1}
        qualifiedAvoidedEnergyKwhTotal={1.1}
      />,
    );
    expect(screen.getByText(/~1\.1 kWh/)).toBeInTheDocument();
    expect(screen.getByText(/never annualized or projected forward/)).toBeInTheDocument();
  });

  it("only renders the full bucket distribution when the caller provides one (org-level only)", () => {
    const { rerender } = render(
      <EnergyEfficiencyPanel
        activeOpportunities={0}
        qualifiedRecoveryCount={0}
        qualifiedAvoidedEnergyKwhTotal={0}
      />,
    );
    expect(screen.queryByText("All monitored assets by energy status")).not.toBeInTheDocument();

    rerender(
      <EnergyEfficiencyPanel
        distribution={{ NORMAL_ENERGY_BEHAVIOR: 2 }}
        activeOpportunities={0}
        qualifiedRecoveryCount={0}
        qualifiedAvoidedEnergyKwhTotal={0}
      />,
    );
    expect(screen.getByText("All monitored assets by energy status")).toBeInTheDocument();
  });
});
