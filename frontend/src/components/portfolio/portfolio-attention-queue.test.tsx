import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PortfolioAttentionQueue } from "@/components/portfolio/portfolio-attention-queue";
import type { AttentionAsset } from "@/lib/api/performance-types";

function asset(overrides: Partial<AttentionAsset> = {}): AttentionAsset {
  return {
    ref: {
      machine_id: "m-1",
      asset_code: "L1-000",
      name: "Test Machine",
      site_id: "s-1",
      site_code: "SITE",
      site_name: "Test Site",
      area: "Test Area",
      criticality: "MEDIUM",
    },
    priority: "HIGH_ATTENTION",
    reasons: ["condition severity HIGH (TEST_CONDITION)"],
    condition_type: "TEST_CONDITION",
    condition_severity: "HIGH",
    ...overrides,
  };
}

describe("PortfolioAttentionQueue", () => {
  it("shows an empty state when nothing needs attention", () => {
    render(<PortfolioAttentionQueue assets={[]} />);
    expect(screen.getByText("Nothing needs attention right now")).toBeInTheDocument();
  });

  it("renders reasons in the backend-given order, not re-sorted", () => {
    render(
      <PortfolioAttentionQueue
        assets={[
          asset({
            reasons: [
              "condition severity HIGH (TEST_CONDITION)",
              "elevated contextual energy demand",
            ],
          }),
        ]}
      />,
    );
    const reasons = screen.getAllByText(/condition severity|elevated contextual/);
    expect(reasons[0]).toHaveTextContent("condition severity HIGH");
    expect(reasons[1]).toHaveTextContent("elevated contextual energy demand");
  });

  it("shows a Data Quality cross-link for a data-limited asset", () => {
    render(
      <PortfolioAttentionQueue
        assets={[
          asset({ priority: "DATA_LIMITED", condition_type: null, condition_severity: null }),
        ]}
      />,
    );
    const link = screen.getByText(/See why — Data Quality/);
    expect(link.closest("a")).toHaveAttribute("href", "/data-quality?machine=m-1");
  });

  it("does not show the Data Quality cross-link for a normally-assessed asset", () => {
    render(<PortfolioAttentionQueue assets={[asset({ priority: "HIGH_ATTENTION" })]} />);
    expect(screen.queryByText(/See why — Data Quality/)).not.toBeInTheDocument();
  });

  it("hides the site name when showSite is false", () => {
    render(<PortfolioAttentionQueue assets={[asset()]} showSite={false} />);
    expect(screen.queryByText(/Test Site/)).not.toBeInTheDocument();
  });

  it("shows the site name by default", () => {
    render(<PortfolioAttentionQueue assets={[asset()]} />);
    expect(screen.getByText(/Test Site/)).toBeInTheDocument();
  });

  it("links the asset name to its machine detail page", () => {
    render(<PortfolioAttentionQueue assets={[asset()]} />);
    expect(screen.getByText("Test Machine").closest("a")).toHaveAttribute("href", "/machines/m-1");
  });
});
