import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MachineEnergyCurrent } from "@/components/energy/machine-energy-current";
import type { EnergyAssessment } from "@/lib/api/energy-types";

function assessment(overrides: Partial<EnergyAssessment> = {}): EnergyAssessment {
  return {
    id: "a-1",
    tenant_id: "t-1",
    machine_id: "m-1",
    power_sensor_id: "s-1",
    as_of_timestamp: new Date().toISOString(),
    actual_power_kw: 43.23,
    expected_power_kw: 38.02,
    expected_lower_kw: 37.46,
    expected_upper_kw: 38.52,
    residual_kw: 5.22,
    residual_pct: 13.72016591812358,
    status: "ELEVATED_ENERGY_DEMAND",
    data_quality_state: "TRUSTED",
    baseline_source: "EXACT_CONTEXT",
    baseline_profile_id: null,
    operating_state: "RUNNING_NORMAL_LOAD",
    engine_version: "1",
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

describe("MachineEnergyCurrent", () => {
  it("states the exact required phrasing, with the correct (non-doubled) percentage", () => {
    render(<MachineEnergyCurrent assessment={assessment()} />);
    expect(
      screen.getByText("Power demand is 13.7% above contextual expectation."),
    ).toBeInTheDocument();
  });

  it("never says 'energy loss due to lubrication'", () => {
    render(<MachineEnergyCurrent assessment={assessment()} />);
    expect(screen.queryByText(/lubrication/i)).not.toBeInTheDocument();
  });

  it("states 'below' for a negative residual", () => {
    render(
      <MachineEnergyCurrent
        assessment={assessment({ residual_pct: -1.6, status: "WITHIN_EXPECTED_RANGE" })}
      />,
    );
    expect(
      screen.getByText("Power demand is 1.6% below contextual expectation."),
    ).toBeInTheDocument();
  });

  it("renders no sentence when residual_pct is null (insufficient data)", () => {
    render(
      <MachineEnergyCurrent
        assessment={assessment({
          residual_pct: null,
          actual_power_kw: null,
          expected_power_kw: null,
          status: "INSUFFICIENT_DATA",
        })}
      />,
    );
    expect(screen.queryByText(/contextual expectation/)).not.toBeInTheDocument();
  });
});
