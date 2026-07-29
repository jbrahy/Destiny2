import { describe, expect, it } from "vitest";
import { compareArmor, Rating } from "./components/ArmorList";
import { ArmorPiece } from "./types";

// Stats sum to `totalStats` so the comparator's total() sees a known value.
function piece(
  name: string,
  { slot = "Helmet", power = 2000, totalStats = 60, isExotic = false } = {},
): ArmorPiece {
  return {
    instanceId: `i-${name}`,
    itemHash: 1,
    name,
    slot,
    className: "Titan",
    power,
    isExotic,
    isMasterworked: false,
    stats: { Mobility: totalStats },
    location: "Vault",
    icon: "",
    equipped: false,
  } as ArmorPiece;
}

function rating(rank: number): Rating {
  return { label: `r${rank}`, color: "#000", rank };
}

/** Sort a list the way ArmorList does, returning names in order. */
function sorted(
  items: { a: ArmorPiece; r: Rating }[],
  sort: Parameters<typeof compareArmor>[2],
): string[] {
  return [...items].sort((x, y) => compareArmor(x, y, sort)).map((i) => i.a.name);
}

describe("compareArmor", () => {
  it("sorts by total stats descending", () => {
    const items = [
      { a: piece("low", { totalStats: 50 }), r: rating(2) },
      { a: piece("high", { totalStats: 70 }), r: rating(2) },
      { a: piece("mid", { totalStats: 60 }), r: rating(2) },
    ];
    expect(sorted(items, "total_desc")).toEqual(["high", "mid", "low"]);
  });

  it("sorts by power descending", () => {
    const items = [
      { a: piece("weak", { power: 1900 }), r: rating(2) },
      { a: piece("strong", { power: 2010 }), r: rating(2) },
    ];
    expect(sorted(items, "power_desc")).toEqual(["strong", "weak"]);
  });

  it("sorts by power ascending", () => {
    const items = [
      { a: piece("strong", { power: 2010 }), r: rating(2) },
      { a: piece("weak", { power: 1900 }), r: rating(2) },
    ];
    expect(sorted(items, "power_asc")).toEqual(["weak", "strong"]);
  });

  it("sorts by rating with the BEST first (lower rank wins)", () => {
    const items = [
      { a: piece("dismantle"), r: rating(4) },
      { a: piece("exotic"), r: rating(0) },
      { a: piece("good"), r: rating(2) },
    ];
    expect(sorted(items, "rating")).toEqual(["exotic", "good", "dismantle"]);
  });

  it("breaks a rating tie on total stats descending", () => {
    const items = [
      { a: piece("sameRankLow", { totalStats: 40 }), r: rating(1) },
      { a: piece("sameRankHigh", { totalStats: 68 }), r: rating(1) },
    ];
    expect(sorted(items, "rating")).toEqual(["sameRankHigh", "sameRankLow"]);
  });

  it("sorts by name A-Z", () => {
    const items = [
      { a: piece("Zephyr"), r: rating(2) },
      { a: piece("Aeon"), r: rating(2) },
      { a: piece("Mask"), r: rating(2) },
    ];
    expect(sorted(items, "name")).toEqual(["Aeon", "Mask", "Zephyr"]);
  });

  it("defaults to Destiny slot order, not alphabetical", () => {
    const items = [
      { a: piece("legs", { slot: "Leg Armor" }), r: rating(2) },
      { a: piece("helm", { slot: "Helmet" }), r: rating(2) },
      { a: piece("chest", { slot: "Chest Armor" }), r: rating(2) },
      { a: piece("arms", { slot: "Gauntlets" }), r: rating(2) },
    ];
    expect(sorted(items, "slot")).toEqual(["helm", "arms", "chest", "legs"]);
  });

  it("breaks a slot tie on total stats descending", () => {
    const items = [
      { a: piece("helmLow", { slot: "Helmet", totalStats: 45 }), r: rating(2) },
      { a: piece("helmHigh", { slot: "Helmet", totalStats: 66 }), r: rating(2) },
    ];
    expect(sorted(items, "slot")).toEqual(["helmHigh", "helmLow"]);
  });

  it("is a consistent comparator — reversing input yields the same order", () => {
    const items = [
      { a: piece("a", { power: 2000, totalStats: 60 }), r: rating(1) },
      { a: piece("b", { power: 1990, totalStats: 65 }), r: rating(2) },
      { a: piece("c", { power: 2005, totalStats: 55 }), r: rating(0) },
    ];
    for (const key of ["total_desc", "power_desc", "power_asc", "rating", "name", "slot"] as const) {
      expect(sorted(items, key)).toEqual(sorted([...items].reverse(), key));
    }
  });

  it("returns 0 for genuinely equal items so sort stays stable", () => {
    const x = { a: piece("same", { power: 2000, totalStats: 60 }), r: rating(2) };
    const y = { a: piece("same", { power: 2000, totalStats: 60 }), r: rating(2) };
    for (const key of ["total_desc", "power_desc", "power_asc", "rating", "name", "slot"] as const) {
      expect(compareArmor(x, y, key)).toBe(0);
    }
  });
});
