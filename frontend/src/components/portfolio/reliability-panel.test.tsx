import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ReliabilityPanel } from "@/components/portfolio/reliability-panel";

describe("ReliabilityPanel", () => {
  it("orders monitor before critical attention regardless of input key order", () => {
    render(<ReliabilityPanel distribution={{ CRITICAL_ATTENTION: 1, MONITOR: 2 }} />);
    const labels = screen.getAllByText(/Monitor|Critical Attention/).map((el) => el.textContent);
    expect(labels.indexOf("Monitor")).toBeLessThan(labels.indexOf("Critical Attention"));
  });

  it("shows the empty label with no assessments", () => {
    render(<ReliabilityPanel distribution={{}} />);
    expect(screen.getByText("No condition assessments recorded yet.")).toBeInTheDocument();
  });
});
