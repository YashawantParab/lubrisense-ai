import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { OpportunityStatePanel } from "@/components/energy/opportunity-state-panel";

describe("OpportunityStatePanel", () => {
  it("never shows avoided energy, a CO2e figure, or 'savings' wording", () => {
    render(
      <OpportunityStatePanel energyStatus="ELEVATED_ENERGY_DEMAND" attributionLevel="POSSIBLE" />,
    );
    expect(screen.queryByText(/kWh/)).not.toBeInTheDocument();
    expect(screen.queryByText(/CO2e/)).not.toBeInTheDocument();
    expect(screen.queryByText(/saving/i)).not.toBeInTheDocument();
    expect(screen.getByText("Not yet verified")).toBeInTheDocument();
  });

  it("marks attribution-supported only when a real attribution level beyond NO_EVIDENCE exists", () => {
    const { rerender } = render(<OpportunityStatePanel energyStatus="ELEVATED_ENERGY_DEMAND" />);
    expect(screen.getByText("Not yet")).toBeInTheDocument();

    rerender(
      <OpportunityStatePanel energyStatus="ELEVATED_ENERGY_DEMAND" attributionLevel="POSSIBLE" />,
    );
    expect(screen.getByText("Yes")).toBeInTheDocument();
  });

  it("shows 'None opened yet' when no maintenance case exists", () => {
    render(<OpportunityStatePanel energyStatus="ELEVATED_ENERGY_DEMAND" />);
    expect(screen.getByText("None opened yet")).toBeInTheDocument();
  });
});
