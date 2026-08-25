import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SegmentedDistributionBar } from "@/components/segmented-distribution-bar";

describe("SegmentedDistributionBar", () => {
  it("renders the empty label when there are no segments", () => {
    render(<SegmentedDistributionBar segments={[]} emptyLabel="Nothing here yet." />);
    expect(screen.getByText("Nothing here yet.")).toBeInTheDocument();
  });

  it("renders each segment's label and count as text, not color alone", () => {
    render(
      <SegmentedDistributionBar
        segments={[
          { key: "a", label: "Monitor", count: 3, colorClass: "bg-emerald-500" },
          { key: "b", label: "Critical Attention", count: 1, colorClass: "bg-red-500" },
        ]}
      />,
    );
    expect(screen.getByText("Monitor")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("Critical Attention")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
  });
});
