import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { KpiStrip } from "@/components/kpi-strip";

describe("KpiStrip", () => {
  it("renders every item's value and label", () => {
    render(
      <KpiStrip
        items={[
          { label: "Need attention", value: 7 },
          { label: "Critical attention", value: 1 },
        ]}
      />,
    );
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("Need attention")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("Critical attention")).toBeInTheDocument();
  });

  it("makes an item clickable only when an href is given", () => {
    render(
      <KpiStrip
        items={[
          { label: "Linked", value: 1, href: "/somewhere" },
          { label: "Plain", value: 2 },
        ]}
      />,
    );
    expect(screen.getByText("Linked").closest("a")).toHaveAttribute("href", "/somewhere");
    expect(screen.getByText("Plain").closest("a")).toBeNull();
  });
});
