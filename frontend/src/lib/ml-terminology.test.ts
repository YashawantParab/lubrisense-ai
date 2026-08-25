import { describe, expect, it } from "vitest";

import { selectableMachinesFor } from "@/lib/ml-terminology";

interface M {
  id: string;
  name: string;
}

const withEvidence: M[] = [
  { id: "m-1", name: "Scored Machine" },
  { id: "m-2", name: "Another Scored Machine" },
];
const noEvidence: M = { id: "m-3", name: "No-Evidence Machine" };
const allMachines: M[] = [...withEvidence, noEvidence];

describe("selectableMachinesFor", () => {
  it("defaults to evidence-only machines — a no-evidence machine never silently appears", () => {
    const result = selectableMachinesFor({
      allMachines,
      machinesWithEvidence: withEvidence,
      showAllAssets: false,
      effectiveMachineId: "m-1",
    });
    expect(result).toEqual(withEvidence);
    expect(result.find((m) => m.id === "m-3")).toBeUndefined();
  });

  it("includes no-evidence machines only when the user opts into 'All assets'", () => {
    const result = selectableMachinesFor({
      allMachines,
      machinesWithEvidence: withEvidence,
      showAllAssets: true,
      effectiveMachineId: "m-1",
    });
    expect(result).toEqual(allMachines);
  });

  it("still resolves a deep-linked no-evidence machine even with the default (evidence-only) scope", () => {
    const result = selectableMachinesFor({
      allMachines,
      machinesWithEvidence: withEvidence,
      showAllAssets: false,
      effectiveMachineId: "m-3",
    });
    expect(result.map((m) => m.id)).toEqual(["m-1", "m-2", "m-3"]);
  });

  it("does not duplicate a machine that is already in the base list", () => {
    const result = selectableMachinesFor({
      allMachines,
      machinesWithEvidence: withEvidence,
      showAllAssets: false,
      effectiveMachineId: "m-2",
    });
    expect(result).toHaveLength(2);
  });
});
