import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConditionBreakdown } from "@/components/portfolio/condition-breakdown";

describe("ConditionBreakdown", () => {
  it("humanizes raw condition-type enum values rather than exposing snake_case", () => {
    render(<ConditionBreakdown distribution={{ DEVELOPING_RESTRICTION_PATTERN: 2 }} />);
    expect(screen.getByText("Developing Restriction Pattern")).toBeInTheDocument();
    expect(screen.queryByText("DEVELOPING_RESTRICTION_PATTERN")).not.toBeInTheDocument();
  });

  it("supports an arbitrary, open condition-type vocabulary without a fixed category list", () => {
    render(
      <ConditionBreakdown
        distribution={{ SOME_FUTURE_CONDITION_TYPE_NOT_YET_KNOWN: 1, NORMAL_OPERATION: 4 }}
      />,
    );
    expect(screen.getByText("Some Future Condition Type Not Yet Known")).toBeInTheDocument();
    expect(screen.getByText("Normal Operation")).toBeInTheDocument();
  });
});
