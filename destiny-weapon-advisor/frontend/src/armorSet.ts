import { ArmorPiece, ArmorSetItem } from "./types";

const SLOTS = ["Helmet", "Gauntlets", "Chest Armor", "Leg Armor", "Class Item"];

export function armorSetItems(chosen: Record<string, ArmorPiece | null>): ArmorSetItem[] {
  const items: ArmorSetItem[] = [];
  for (const slot of SLOTS) {
    const p = chosen[slot];
    if (p) items.push({ instanceId: p.instanceId, itemHash: p.itemHash, slot, name: p.name });
  }
  return items;
}

export function armorSetTier(chosen: Record<string, ArmorPiece | null>): number {
  let total = 0;
  for (const slot of SLOTS) {
    const p = chosen[slot];
    if (p) total += Object.values(p.stats).reduce((a, b) => a + b, 0);
  }
  return Math.floor(total / 10);
}
