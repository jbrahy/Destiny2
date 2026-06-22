import { describe, expect, it } from "vitest";
import { suggestedItems } from "./loadoutSuggestion";
import { LoadoutSuggestion } from "./types";

function weapon(instanceId: string, itemHash: number) {
  return {
    instanceId, itemHash, name: "Gun", weaponType: "Hand Cannon", element: "Void",
    location: "Vault", isMasterworked: false, verdict: "good" as const, matchedPerks: [],
    note: "", verdictReason: "", upgradePath: null,
    tags: [], isDuplicate: false, power: 0, ammoType: "Primary",
    frame: "Adaptive", perkNames: [], stats: {}, ratedPerks: [], icon: "", equipped: false,
  };
}

const base: LoadoutSuggestion = {
  activity: "Raid",
  subclass: { class: "Titan", subclass: "Strand", build: null },
  weapons: { Primary: null, Special: null, Heavy: null },
  elementCoverage: { elements: [], activityElement: null, matchesActivity: false },
  guidance: "",
};

describe("suggestedItems", () => {
  it("returns transfer items for non-null chosen weapons only", () => {
    const s: LoadoutSuggestion = {
      ...base,
      weapons: { Primary: weapon("a", 1), Special: null, Heavy: weapon("c", 3) },
    };
    expect(suggestedItems(s)).toEqual([
      { instanceId: "a", itemHash: 1 },
      { instanceId: "c", itemHash: 3 },
    ]);
  });

  it("returns empty array when no weapons chosen", () => {
    expect(suggestedItems(base)).toEqual([]);
  });
});
