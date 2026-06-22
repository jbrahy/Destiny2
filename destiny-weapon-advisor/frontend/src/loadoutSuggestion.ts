import { LoadoutItem, LoadoutSuggestion } from "./types";

const SLOTS: ("Primary" | "Special" | "Heavy")[] = ["Primary", "Special", "Heavy"];

export function suggestedItems(s: LoadoutSuggestion): LoadoutItem[] {
  return SLOTS.map((slot) => s.weapons[slot])
    .filter((w): w is NonNullable<typeof w> => w !== null)
    .map((w) => ({ instanceId: w.instanceId, itemHash: w.itemHash }));
}
