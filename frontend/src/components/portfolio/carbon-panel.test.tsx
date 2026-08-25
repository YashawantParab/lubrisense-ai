import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CarbonPanel } from "@/components/portfolio/carbon-panel";

describe("CarbonPanel", () => {
  it("never shows '0 kg CO2e' when no qualifying outcome exists — shows unavailable text instead", () => {
    render(<CarbonPanel estimatedCo2eKgTotal={0} qualifyingOutcomeCount={0} />);
    expect(screen.queryByText(/0.00 kg CO2e/)).not.toBeInTheDocument();
    expect(screen.getByText(/not a zero impact/)).toBeInTheDocument();
  });

  it("shows the real figure and outcome count when a qualifying outcome exists", () => {
    render(<CarbonPanel estimatedCo2eKgTotal={0.43} qualifyingOutcomeCount={1} />);
    expect(screen.getByText("0.43 kg CO2e")).toBeInTheDocument();
    expect(screen.getByText(/1 qualifying outcome/)).toBeInTheDocument();
  });

  it("never claims 'carbon saved' or 'carbon reduction achieved'", () => {
    render(<CarbonPanel estimatedCo2eKgTotal={0.43} qualifyingOutcomeCount={1} />);
    expect(screen.queryByText(/carbon reduction achieved/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Never a claim of/)).toBeInTheDocument();
  });

  it("surfaces outcomes missing an applicable emission factor when present", () => {
    render(
      <CarbonPanel estimatedCo2eKgTotal={0.43} qualifyingOutcomeCount={1} missingFactorCount={2} />,
    );
    expect(
      screen.getByText(/2 qualified outcomes missing an applicable emission factor/),
    ).toBeInTheDocument();
  });

  it("falls back to the total when no explicit qualifying-outcome count is given (area level)", () => {
    render(<CarbonPanel estimatedCo2eKgTotal={0.43} />);
    expect(screen.getByText("0.43 kg CO2e")).toBeInTheDocument();
  });
});
