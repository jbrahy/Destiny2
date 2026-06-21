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
}
