import {
  ActivityRec, ArmorPiece, Build, Character, Loadout, LoadoutItem, Membership, MoveResult,
  PostmasterItem, WeaponDto, WeaponTypePerks,
} from "./types";

export const loginUrl = "/api/login";

export async function fetchStatus(): Promise<boolean> {
  const res = await fetch("/api/status");
  const data = await res.json();
  return data.authenticated as boolean;
}

export interface WeaponsResponse {
  weapons: WeaponDto[];
  cachedAt?: number;
}

export async function fetchWeapons(refresh = false): Promise<WeaponsResponse> {
  const res = await fetch(`/api/weapons${refresh ? "?refresh=1" : ""}`);
  if (!res.ok) throw new Error(`Failed to load weapons (${res.status})`);
  return (await res.json()) as WeaponsResponse;
}

export async function fetchPerks(): Promise<WeaponTypePerks[]> {
  const res = await fetch("/api/perks");
  if (!res.ok) throw new Error(`Failed to load perks (${res.status})`);
  return (await res.json()).weaponTypes as WeaponTypePerks[];
}

export async function savePerkRating(body: {
  name: string; weaponType: string; rating: string; reason: string; tags: string[]; notes: string;
}): Promise<void> {
  const res = await fetch("/api/perks", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Failed to save rating (${res.status})`);
}

export async function fetchMemberships(): Promise<{
  memberships: Membership[];
  active: { type: number; id: string } | null;
}> {
  const res = await fetch("/api/memberships");
  if (!res.ok) throw new Error(`Failed to load accounts (${res.status})`);
  return res.json();
}

export async function selectMembership(membershipType: number, membershipId: string): Promise<void> {
  const res = await fetch("/api/memberships/select", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ membershipType, membershipId }),
  });
  if (!res.ok) throw new Error(`Failed to switch account (${res.status})`);
}

export async function fetchBuilds(): Promise<Record<string, Build>> {
  const res = await fetch("/api/builds");
  if (!res.ok) throw new Error(`Failed to load builds (${res.status})`);
  return (await res.json()).builds as Record<string, Build>;
}

export async function saveBuild(key: string, data: Build): Promise<void> {
  const res = await fetch("/api/builds", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, data }),
  });
  if (!res.ok) throw new Error(`Failed to save build (${res.status})`);
}

export async function fetchActivities(): Promise<ActivityRec[]> {
  const res = await fetch("/api/activities");
  if (!res.ok) throw new Error(`Failed to load activities (${res.status})`);
  return (await res.json()).activities as ActivityRec[];
}

export async function saveActivity(name: string, data: ActivityRec): Promise<void> {
  const res = await fetch("/api/activities", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, data }),
  });
  if (!res.ok) throw new Error(`Failed to save activity (${res.status})`);
}

export async function fetchTags(): Promise<Record<string, string>> {
  const res = await fetch("/api/tags");
  if (!res.ok) throw new Error(`Failed to load tags (${res.status})`);
  return (await res.json()).tags as Record<string, string>;
}

export async function saveTag(instanceId: string, tag: string): Promise<void> {
  const res = await fetch("/api/tags", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ instanceId, tag }),
  });
  if (!res.ok) throw new Error(`Failed to save tag (${res.status})`);
}

export async function fetchArmor(): Promise<{ armor: ArmorPiece[]; statNames: string[] }> {
  const res = await fetch("/api/armor");
  if (!res.ok) throw new Error(`Failed to load armor (${res.status})`);
  return res.json();
}

export async function fetchCounts(): Promise<{
  weapons: number; armor: number; vaultWeapons: number; vaultArmor: number;
}> {
  const res = await fetch("/api/counts");
  if (!res.ok) throw new Error(`Failed to load counts (${res.status})`);
  return res.json();
}

export async function fetchCharacters(): Promise<Character[]> {
  const res = await fetch("/api/characters");
  if (!res.ok) throw new Error(`Failed to load characters (${res.status})`);
  return (await res.json()).characters as Character[];
}

export async function moveItem(body: {
  instanceId: string; itemHash: number; targetCharacterId: string; equip: boolean;
}): Promise<void> {
  const res = await fetch("/api/transfer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(data.detail || `Move failed (${res.status})`);
  }
}

export async function bulkMove(
  items: LoadoutItem[], targetCharacterId: string, equip: boolean,
): Promise<MoveResult[]> {
  const res = await fetch("/api/transfer/bulk", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items, targetCharacterId, equip }),
  });
  if (!res.ok) throw new Error(`Bulk move failed (${res.status})`);
  return (await res.json()).results as MoveResult[];
}

export async function fetchLoadouts(): Promise<Loadout[]> {
  const res = await fetch("/api/loadouts");
  if (!res.ok) throw new Error(`Failed to load loadouts (${res.status})`);
  return (await res.json()).loadouts as Loadout[];
}

export async function saveLoadout(name: string, characterId: string, items: LoadoutItem[]): Promise<void> {
  const res = await fetch("/api/loadouts", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, characterId, items }),
  });
  if (!res.ok) throw new Error(`Failed to save loadout (${res.status})`);
}

export async function deleteLoadout(name: string): Promise<void> {
  const res = await fetch(`/api/loadouts/${encodeURIComponent(name)}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Failed to delete loadout (${res.status})`);
}

export async function applyLoadout(name: string): Promise<MoveResult[]> {
  const res = await fetch("/api/loadouts/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(data.detail || `Apply failed (${res.status})`);
  }
  return (await res.json()).results as MoveResult[];
}

export async function fetchPostmaster(): Promise<PostmasterItem[]> {
  const res = await fetch("/api/postmaster");
  if (!res.ok) throw new Error(`Failed to load postmaster (${res.status})`);
  return (await res.json()).items as PostmasterItem[];
}

export async function pullPostmaster(item: PostmasterItem): Promise<void> {
  const res = await fetch("/api/postmaster/pull", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      itemHash: item.itemHash, instanceId: item.instanceId,
      characterId: item.characterId, stackSize: item.quantity,
    }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(data.detail || `Pull failed (${res.status})`);
  }
}
