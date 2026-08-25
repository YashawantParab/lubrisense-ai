import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AreaPerformanceTable } from "@/components/portfolio/area-performance-table";
import type { AreaPerformance } from "@/lib/api/performance-types";

function area(overrides: Partial<AreaPerformance> = {}): AreaPerformance {
  return {
    area: "Test Area",
    as_of: new Date().toISOString(),
    site_codes: ["SITE_A"],
    asset_count: 2,
    condition_distribution: {},
    attention_count: 0,
    critical_attention_count: 0,
    action_readiness_distribution: {},
    data_trust_distribution: {},
    active_energy_opportunities: 0,
    qualified_recovery_count: 0,
    qualified_avoided_energy_kwh_total: 0,
    estimated_co2e_kg_total: 0,
    provenance: "MEASURED_PLATFORM_METRIC",
    policy_version: "1",
    ...overrides,
  };
}

describe("AreaPerformanceTable", () => {
  it("shows an empty state with no areas", () => {
    render(<AreaPerformanceTable areas={[]} />);
    expect(screen.getByText("No areas yet")).toBeInTheDocument();
  });

  it("discloses other sites an area is also active at, rather than implying a site-scoped number", () => {
    render(
      <AreaPerformanceTable
        areas={[area({ area: "Pyroprocessing", site_codes: ["HARBOR", "RIDGE"] })]}
        currentSiteCode="HARBOR"
      />,
    );
    expect(screen.getByText(/Also active at RIDGE/)).toBeInTheDocument();
  });

  it("does not show the disclosure for a single-site area", () => {
    render(
      <AreaPerformanceTable
        areas={[area({ area: "Crushing", site_codes: ["HARBOR"] })]}
        currentSiteCode="HARBOR"
      />,
    );
    expect(screen.queryByText(/Also active at/)).not.toBeInTheDocument();
  });

  it("links each area to its (organization-wide) detail page, percent-encoding a slash in the name", () => {
    render(<AreaPerformanceTable areas={[area({ area: "Metals / Rolling" })]} />);
    expect(screen.getByText("Metals / Rolling").closest("a")).toHaveAttribute(
      "href",
      "/performance/areas/Metals%20%2F%20Rolling",
    );
  });
});
