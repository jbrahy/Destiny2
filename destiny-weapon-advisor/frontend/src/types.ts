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
  tags: string[];
  isDuplicate: boolean;
  power: number;
  ammoType: string;
  frame: string;
  perkNames: string[];
  stats: Record<string, number>;
  ratedPerks: RatedPerk[];
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
  tags: string[];
  isOverride: boolean;
  dirty?: boolean;
}

export interface WeaponTypePerks {
  weaponType: string;
  perks: CatalogPerk[];
}
