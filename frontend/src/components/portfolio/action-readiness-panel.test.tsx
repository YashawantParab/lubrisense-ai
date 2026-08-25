import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ActionReadinessPanel } from "@/components/portfolio/action-readiness-panel";

describe("ActionReadinessPanel", () => {
  it("never renders a fabricated auto-eligible or safety-interlock category", () => {
    render(
      <ActionReadinessPanel
        distribution={{
          MONITORING_ONLY: 2,
          HUMAN_ACTION_REQUIRED: 1,
          ASSESSMENT_BLOCKED: 1,
        }}
      />,
    );
    expect(screen.queryByText(/Auto Eligible/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Safety Interlock/i)).not.toBeInTheDocument();
    expect(screen.getByText("Human Action Required")).toBeInTheDocument();
  });

  it("shows the empty label when nothing is assessed yet", () => {
    render(<ActionReadinessPanel distribution={{}} />);
    expect(screen.getByText("No assets assessed yet.")).toBeInTheDocument();
  });
});
