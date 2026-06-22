export type Verdict = "god_roll" | "good" | "upgrade" | "no_data" | "dismantle";

export interface ArmorPiece {
  instanceId: string;
  itemHash: number;
  name: string;
  slot: string;
  className: string;
  power: number;
  isExotic: boolean;
  isMasterworked: boolean;
  stats: Record<string, number>;
  location: string;
  icon: string;
  equipped: boolean;
}

export type Build = Record<string, string>;

export interface ActivityRec {
  name: string;
  type: string;
  recommendedClass: string;
  recommendedSubclass: string;
  weapons: string;
  notes: string;
}

export interface Membership {
  type: number;
  id: string;
  displayName: string;
}

export interface LoadoutItem {
  instanceId: string;
  itemHash: number;
}

export interface Loadout {
  name: string;
  characterId: string;
  items: LoadoutItem[];
}

export interface PostmasterItem {
  instanceId: string;
  itemHash: number;
  name: string;
  icon: string;
  characterId: string;
  className: string;
  quantity: number;
}

export interface MoveResult {
  instanceId: string;
  ok: boolean;
  error?: string;
}

export interface Character {
  id: string;
  className: string;
  light: number;
  lastPlayed: string;
  current: boolean;
}

export interface WeaponDto {
  instanceId: string;
  itemHash: number;
  name: string;
  weaponType: string;
  element: string;
  location: string;
  isMasterworked: boolean;
  verdict: Verdict;
  matchedPerks: string[];
  note: string;
  verdictReason: string;
  upgradePath: string | null;
  tags: string[];
  isDuplicate: boolean;
  power: number;
  ammoType: string;
  frame: string;
  perkNames: string[];
  stats: Record<string, number>;
  ratedPerks: RatedPerk[];
  icon: string;
  equipped: boolean;
}

export interface RatedPerk {
  name: string;
  rating: string;
  reason: string;
  tags: string[];
}

export interface CatalogPerk {
  name: string;
  rating: string;
  reason: string;
  notes: string;
  description: string;
  icon: string;
  tags: string[];
  isOverride: boolean;
  dirty?: boolean;
}

export interface WeaponTypePerks {
  weaponType: string;
  perks: CatalogPerk[];
}

export type RecommendedWeapon = WeaponDto & { recommendReason: string };

export interface Recommendations {
  context: string;
  slots: Record<"Primary" | "Special" | "Heavy", RecommendedWeapon[]>;
}

export interface LoadoutSuggestion {
  activity: string;
  subclass: { class: string; subclass: string; build: Build | null };
  weapons: Record<"Primary" | "Special" | "Heavy", (WeaponDto & { recommendReason?: string }) | null>;
  elementCoverage: { elements: string[]; activityElement: string | null; matchesActivity: boolean };
  guidance: string;
}

export interface ArmorSetItem {
  instanceId: string;
  itemHash: number;
  slot: string;
  name: string;
}

export interface ArmorSet {
  name: string;
  className: string;
  characterId: string;
  tier: number;
  items: ArmorSetItem[];
}
