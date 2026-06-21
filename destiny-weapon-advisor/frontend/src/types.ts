export type Verdict = "god_roll" | "good" | "upgrade" | "no_data" | "dismantle";

export interface WeaponDto {
  instanceId: string;
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
  tags: string[];
  isOverride: boolean;
}

export interface WeaponTypePerks {
  weaponType: string;
  perks: CatalogPerk[];
}
