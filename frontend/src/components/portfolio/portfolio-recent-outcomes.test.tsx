import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PortfolioRecentOutcomes } from "@/components/portfolio/portfolio-recent-outcomes";
import type { RecentOutcome } from "@/lib/api/performance-types";

const ref = {
  machine_id: "m-1",
  asset_code: "L1-000",
  name: "Bucket Elevator BE-201",
  site_id: "s-1",
  site_code: "EASTGATE",
  site_name: "Eastgate Site",
  area: "Bulk Material Handling",
  criticality: "HIGH",
};

describe("PortfolioRecentOutcomes", () => {
  it("shows an empty state when there are no outcomes", () => {
    render(<PortfolioRecentOutcomes outcomes={[]} />);
    expect(screen.getByText("No outcomes yet")).toBeInTheDocument();
  });

  it("visually differentiates different outcome types rather than treating them identically", () => {
    const outcomes: RecentOutcome[] = [
      {
        outcome_type: "QUALIFIED_ENERGY_RECOVERY",
        ref,
        occurred_at: new Date().toISOString(),
        summary: "Qualified energy recovery observed (~1.1 kWh)",
        provenance: "MEASURED_PLATFORM_METRIC",
      },
      {
        outcome_type: "CARBON_ESTIMATE_PRODUCED",
        ref,
        occurred_at: new Date().toISOString(),
        summary: "Estimated CO2e impact computed (~0.43 kg)",
        provenance: "DEMO_ESTIMATE",
      },
    ];
    render(<PortfolioRecentOutcomes outcomes={outcomes} />);
    expect(screen.getByText("Qualified Energy Recovery")).toBeInTheDocument();
    expect(screen.getByText("Carbon Estimate Produced")).toBeInTheDocument();
    expect(screen.getByText("Qualified energy recovery observed (~1.1 kWh)")).toBeInTheDocument();
  });

  it("links each outcome to its machine detail page", () => {
    render(
      <PortfolioRecentOutcomes
        outcomes={[
          {
            outcome_type: "CONDITION_RESOLVED",
            ref,
            occurred_at: new Date().toISOString(),
            summary: "Condition resolved: NORMAL_OPERATION",
            provenance: "MEASURED_PLATFORM_METRIC",
          },
        ]}
      />,
    );
    expect(screen.getByText("Bucket Elevator BE-201").closest("a")).toHaveAttribute(
      "href",
      "/machines/m-1",
    );
  });
});
