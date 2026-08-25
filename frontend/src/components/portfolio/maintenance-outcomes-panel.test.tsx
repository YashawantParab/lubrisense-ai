import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MaintenanceOutcomesPanel } from "@/components/portfolio/maintenance-outcomes-panel";

describe("MaintenanceOutcomesPanel", () => {
  it("distinguishes a qualified recovery from a deteriorated outcome — never one 'completed' bucket", () => {
    render(
      <MaintenanceOutcomesPanel
        distribution={{ COMPLETED_QUALIFIED_RECOVERY: 1, COMPLETED_DETERIORATED: 1 }}
      />,
    );
    expect(screen.getByText("Completed Qualified Recovery")).toBeInTheDocument();
    expect(screen.getByText("Completed Deteriorated")).toBeInTheDocument();
  });

  it("shows the empty label when nothing has happened yet", () => {
    render(<MaintenanceOutcomesPanel distribution={{}} />);
    expect(screen.getByText("No maintenance actions recorded yet.")).toBeInTheDocument();
  });

  it("shows overdue actions only when present", () => {
    const { rerender } = render(
      <MaintenanceOutcomesPanel distribution={{}} openActions={2} overdueActions={0} />,
    );
    expect(screen.queryByText("overdue")).not.toBeInTheDocument();

    rerender(<MaintenanceOutcomesPanel distribution={{}} openActions={2} overdueActions={1} />);
    expect(screen.getByText("overdue")).toBeInTheDocument();
  });
});
