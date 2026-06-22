import { describe, expect, it } from "vitest";
import { armorSetItems, armorSetTier } from "./armorSet";
import { ArmorPiece } from "./types";

function piece(p: Partial<ArmorPiece>): ArmorPiece {
  return {
    instanceId: "i", itemHash: 1, name: "Piece", slot: "Helmet", className: "Warlock",
    power: 0, isExotic: false, isMasterworked: false, stats: {}, location: "Vault",
    icon: "", equipped: false, ...p,
  };
}

describe("armorSetItems", () => {
  it("maps non-null pieces in canonical slot order, skipping empties", () => {
    const chosen = {
      "Helmet": piece({ instanceId: "h", itemHash: 10, slot: "Helmet", name: "Helm" }),
      "Gauntlets": null,
      "Chest Armor": piece({ instanceId: "c", itemHash: 30, slot: "Chest Armor", name: "Chest" }),
      "Leg Armor": null,
      "Class Item": piece({ instanceId: "ci", itemHash: 50, slot: "Class Item", name: "Bond" }),
    };
    expect(armorSetItems(chosen)).toEqual([
      { instanceId: "h", itemHash: 10, slot: "Helmet", name: "Helm" },
      { instanceId: "c", itemHash: 30, slot: "Chest Armor", name: "Chest" },
      { instanceId: "ci", itemHash: 50, slot: "Class Item", name: "Bond" },
    ]);
  });

  it("returns empty array when all slots null", () => {
    expect(armorSetItems({ Helmet: null, Gauntlets: null })).toEqual([]);
  });
});

describe("armorSetTier", () => {
  it("floors the sum of all stat values over 10", () => {
    const chosen = {
      "Helmet": piece({ stats: { Class: 30, Health: 5 } }),  // 35
      "Class Item": piece({ stats: { Class: 40, Melee: 15 } }),  // 55
    };
    // total 90 -> tier 9
    expect(armorSetTier(chosen)).toBe(9);
  });

  it("is 0 for an all-null set", () => {
    expect(armorSetTier({ Helmet: null })).toBe(0);
  });
});
