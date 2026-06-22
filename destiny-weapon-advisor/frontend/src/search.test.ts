import { describe, expect, it } from "vitest";
import { matchArmor, matchWeapon, parseQuery } from "./search";
import { ArmorPiece, WeaponDto } from "./types";

function weapon(p: Partial<WeaponDto>): WeaponDto {
  return {
    instanceId: "i", itemHash: 1, name: "Gun", weaponType: "Hand Cannon", element: "Void",
    location: "Vault", isMasterworked: false, verdict: "good", matchedPerks: [], note: "",
    tags: [], isDuplicate: false, power: 0, ammoType: "Primary", frame: "Adaptive Frame",
    perkNames: [], stats: {}, ratedPerks: [], icon: "", equipped: false, ...p,
  };
}

function armor(p: Partial<ArmorPiece>): ArmorPiece {
  return {
    instanceId: "a", itemHash: 1, name: "Helm", slot: "Helmet", className: "Hunter", power: 0,
    isExotic: false, isMasterworked: false, stats: {}, location: "Vault", icon: "",
    equipped: false, ...p,
  };
}

describe("parseQuery", () => {
  it("splits key:value pairs and free terms", () => {
    expect(parseQuery("type:pulse outlaw")).toEqual([
      { key: "type", value: "pulse" },
      { key: null, value: "outlaw" },
    ]);
  });
});

describe("matchWeapon", () => {
  it("matches type, element, is:masterwork, perk", () => {
    const w = weapon({ weaponType: "Pulse Rifle", element: "Void", isMasterworked: true, perkNames: ["Outlaw"] });
    expect(matchWeapon(w, "", parseQuery("type:pulse"))).toBe(true);
    expect(matchWeapon(w, "", parseQuery("element:void is:masterwork"))).toBe(true);
    expect(matchWeapon(w, "", parseQuery("perk:outlaw"))).toBe(true);
    expect(matchWeapon(w, "", parseQuery("type:hand"))).toBe(false);
  });

  it("free text matches name", () => {
    expect(matchWeapon(weapon({ name: "Fatebringer" }), "", parseQuery("fate"))).toBe(true);
    expect(matchWeapon(weapon({ name: "Fatebringer" }), "", parseQuery("nope"))).toBe(false);
  });

  it("filters by tag", () => {
    expect(matchWeapon(weapon({}), "keep", parseQuery("tag:keep"))).toBe(true);
    expect(matchWeapon(weapon({}), "junk", parseQuery("tag:keep"))).toBe(false);
  });
});

describe("matchArmor", () => {
  it("matches slot, is:exotic, rating", () => {
    const a = armor({ slot: "Chest Armor", isExotic: true });
    expect(matchArmor(a, "", "Top Roll", parseQuery("slot:chest"))).toBe(true);
    expect(matchArmor(a, "", "Top Roll", parseQuery("is:exotic"))).toBe(true);
    expect(matchArmor(a, "", "Top Roll", parseQuery("rating:top"))).toBe(true);
    expect(matchArmor(a, "", "Top Roll", parseQuery("slot:helmet"))).toBe(false);
  });
});
