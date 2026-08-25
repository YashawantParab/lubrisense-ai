import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SitePerformanceTable } from "@/components/portfolio/site-performance-table";
import type { SitePerformance } from "@/lib/api/performance-types";

function site(overrides: Partial<SitePerformance> = {}): SitePerformance {
  return {
    site_id: "s-1",
    site_code: "SITE",
    site_name: "Test Site",
    as_of: new Date().toISOString(),
    asset_count: 4,
    condition_distribution: {},
    attention_count: 0,
    critical_attention_count: 0,
    active_incidents: 0,
    open_maintenance_actions: 0,
    action_readiness_distribution: {},
    data_trust_distribution: {},
    active_energy_opportunities: 0,
    attribution_supported_opportunities: 0,
    qualified_recovery_count: 0,
    qualified_avoided_energy_kwh_total: 0,
    carbon_estimate_available_count: 0,
    estimated_co2e_kg_total: 0,
    open_maintenance_outcome_distribution: {},
    recent_outcomes: [],
    top_attention_assets: [],
    provenance: "MEASURED_PLATFORM_METRIC",
    policy_version: "1",
    ...overrides,
  };
}

describe("SitePerformanceTable", () => {
  it("shows an empty state with no sites", () => {
    render(<SitePerformanceTable sites={[]} />);
    expect(screen.getByText("No sites yet")).toBeInTheDocument();
  });

  it("ranks critical-attention sites above merely-attention sites, using real counts only", () => {
    render(
      <SitePerformanceTable
        sites={[
          site({
            site_id: "low",
            site_name: "Low Site",
            attention_count: 5,
            critical_attention_count: 0,
          }),
          site({
            site_id: "high",
            site_name: "High Site",
            attention_count: 1,
            critical_attention_count: 1,
          }),
        ]}
      />,
    );
    const rows = screen.getAllByRole("row").slice(1); // skip header row
    expect(rows[0]).toHaveTextContent("High Site");
    expect(rows[1]).toHaveTextContent("Low Site");
  });

  it("links each site to its detail page", () => {
    render(<SitePerformanceTable sites={[site()]} />);
    expect(screen.getByText("Test Site").closest("a")).toHaveAttribute(
      "href",
      "/performance/sites/s-1",
    );
  });
});
