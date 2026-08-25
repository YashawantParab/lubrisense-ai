import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DataTrustPanel } from "@/components/portfolio/data-trust-panel";

describe("DataTrustPanel", () => {
  it("surfaces a blocked critical asset even when the overall distribution reads mostly trusted", () => {
    render(
      <DataTrustPanel
        distribution={{ DECISION_EVIDENCE_TRUSTED: 95, ASSESSMENT_BLOCKED: 5 }}
        criticalAssetsLimited={1}
      />,
    );
    expect(
      screen.getByText(/1 critical asset currently has limited decision evidence/),
    ).toBeInTheDocument();
  });

  it("does not show the critical-asset banner when there are none", () => {
    render(
      <DataTrustPanel distribution={{ DECISION_EVIDENCE_TRUSTED: 10 }} criticalAssetsLimited={0} />,
    );
    expect(screen.queryByText(/critical asset/)).not.toBeInTheDocument();
  });

  it("never shows a bare percentage as the only signal — categories are labeled", () => {
    render(
      <DataTrustPanel distribution={{ DECISION_EVIDENCE_TRUSTED: 10, CONFIDENCE_REDUCED: 1 }} />,
    );
    expect(screen.getByText("Decision Evidence Trusted")).toBeInTheDocument();
    expect(screen.getByText("Confidence Reduced")).toBeInTheDocument();
  });
});
