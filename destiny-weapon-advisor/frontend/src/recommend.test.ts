import { describe, expect, it } from "vitest";
import { buildContextOptions } from "./recommend";
import { ActivityRec } from "./types";

function activity(name: string): ActivityRec {
  return {
    name, type: "Raid", recommendedClass: "Any", recommendedSubclass: "Solar",
    weapons: "", notes: "",
  };
}

describe("buildContextOptions", () => {
  it("prepends general modes then lists activities", () => {
    const opts = buildContextOptions([activity("Crota's End"), activity("Last Wish")]);
    expect(opts).toEqual([
      { value: "general-pve", label: "General (PvE)" },
      { value: "general-pvp", label: "General (PvP)" },
      { value: "Crota's End", label: "Crota's End" },
      { value: "Last Wish", label: "Last Wish" },
    ]);
  });

  it("works with no activities", () => {
    expect(buildContextOptions([])).toEqual([
      { value: "general-pve", label: "General (PvE)" },
      { value: "general-pvp", label: "General (PvP)" },
    ]);
  });
});
