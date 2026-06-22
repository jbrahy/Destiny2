import { ArmorPiece, WeaponDto } from "./types";

export interface Term {
  key: string | null;
  value: string;
}

// Parse "type:pulse element:void is:masterwork outlaw" into terms.
export function parseQuery(q: string): Term[] {
  return q.trim().toLowerCase().split(/\s+/).filter(Boolean).map((tok) => {
    const i = tok.indexOf(":");
    return i > 0 ? { key: tok.slice(0, i), value: tok.slice(i + 1) } : { key: null, value: tok };
  });
}

export function matchWeapon(w: WeaponDto, tag: string, terms: Term[]): boolean {
  return terms.every((t) => {
    const v = t.value;
    if (!t.key) {
      return w.name.toLowerCase().includes(v) || w.frame.toLowerCase().includes(v)
        || w.perkNames.some((p) => p.toLowerCase().includes(v));
    }
    switch (t.key) {
      case "type": return w.weaponType.toLowerCase().includes(v);
      case "element": return w.element.toLowerCase().includes(v);
      case "ammo": return w.ammoType.toLowerCase().includes(v);
      case "frame": return w.frame.toLowerCase().includes(v);
      case "perk": return w.perkNames.some((p) => p.toLowerCase().includes(v));
      case "rating":
      case "verdict": return w.verdict.replace("_", "").includes(v.replace("_", ""));
      case "tag": return (tag || "").toLowerCase() === v;
      case "loc":
      case "location": return w.location.toLowerCase().includes(v);
      case "is":
        if (v === "masterwork" || v === "mw") return w.isMasterworked;
        if (v === "dupe" || v === "duplicate") return w.isDuplicate;
        if (v === "equipped") return w.equipped;
        return true;
      default: return w.name.toLowerCase().includes(v);
    }
  });
}

export function matchArmor(a: ArmorPiece, tag: string, ratingLabel: string, terms: Term[]): boolean {
  return terms.every((t) => {
    const v = t.value;
    if (!t.key) return a.name.toLowerCase().includes(v);
    switch (t.key) {
      case "slot": return a.slot.toLowerCase().includes(v);
      case "class": return a.className.toLowerCase().includes(v);
      case "rating": return ratingLabel.toLowerCase().replace("?", "").includes(v.replace("?", ""));
      case "tag": return (tag || "").toLowerCase() === v;
      case "loc":
      case "location": return a.location.toLowerCase().includes(v);
      case "is":
        if (v === "exotic") return a.isExotic;
        if (v === "masterwork" || v === "mw") return a.isMasterworked;
        if (v === "equipped") return a.equipped;
        return true;
      default: return a.name.toLowerCase().includes(v);
    }
  });
}
