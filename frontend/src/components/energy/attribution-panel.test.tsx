import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AttributionPanel } from "@/components/energy/attribution-panel";
import type { Attribution } from "@/lib/api/energy-types";

function attribution(overrides: Partial<Attribution> = {}): Attribution {
  return {
    id: "a-1",
    tenant_id: "t-1",
    machine_id: "m-1",
    energy_assessment_id: "e-1",
    as_of_timestamp: new Date().toISOString(),
    attribution_level: "POSSIBLE",
    energy_residual_kw: 5.22,
    energy_residual_pct: 13.72016591812358,
    supporting_evidence: ["Machine power is +13.7% above its contextual expected range."],
    contradicting_evidence: ["Current condition attributes this to an independent cause."],
    limiting_factors: [],
    alternative_explanations: [],
    data_quality_state: "TRUSTED",
    condition_assessment_id: null,
    policy_version: "1",
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

describe("AttributionPanel", () => {
  it("shows energy deviation and lubrication attribution as two visually separate blocks", () => {
    render(<AttributionPanel attribution={attribution()} />);
    expect(screen.getByText("Energy deviation")).toBeInTheDocument();
    expect(screen.getByText("Lubrication attribution")).toBeInTheDocument();
    expect(screen.getByText("+13.7%")).toBeInTheDocument();
    expect(screen.getByText("Possible")).toBeInTheDocument();
  });

  it("never implies the deviation percentage is itself a lubrication figure", () => {
    render(<AttributionPanel attribution={attribution()} />);
    expect(screen.getByText(/never a percentage of the deviation itself/)).toBeInTheDocument();
  });

  it("renders supporting, contradicting, limiting, and alternative evidence separately", () => {
    render(
      <AttributionPanel
        attribution={attribution({
          limiting_factors: ["Sensor coverage limited"],
          alternative_explanations: ["Process load change"],
        })}
      />,
    );
    expect(screen.getByText("Supporting evidence")).toBeInTheDocument();
    expect(screen.getByText("Contradicting evidence")).toBeInTheDocument();
    expect(screen.getByText("Limiting factors")).toBeInTheDocument();
    expect(screen.getByText("Alternative explanations")).toBeInTheDocument();
  });
});
