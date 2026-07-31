import {
  ActivityRec, ArmorPiece, ArmorSet, Build, Character, Loadout, LoadoutItem, LoadoutSuggestion, Membership, MoveResult,
  PostmasterItem, Recommendations, WeaponDto, WeaponTypePerks,
} from "./types";

export const loginUrl = "/api/login";

/** Read a cookie value by name from document.cookie. Returns undefined if absent. */
export function getCookie(name: string): string | undefined {
  const match = document.cookie
    .split(";")
    .map((c) => c.trim())
    .find((c) => c.startsWith(`${name}=`));
  return match ? match.slice(name.length + 1) : undefined;
}

const MUTATING = new Set(["POST", "PUT", "DELETE"]);

/** Central fetch wrapper: attaches credentials + CSRF header on mutating requests,
 *  and redirects to /api/login on any 401. */
async function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const method = (init.method ?? "GET").toUpperCase();
  const baseHeaders: Record<string, string> = { ...(init.headers as Record<string, string>) };

  if (MUTATING.has(method)) {
    const csrf = getCookie("csrftoken");
    if (csrf) baseHeaders["X-CSRF-Token"] = csrf;
  }

  const res = await fetch(url, {
    ...init,
    credentials: "same-origin",
    headers: baseHeaders,
  });

  if (res.status === 401) {
    window.location.href = loginUrl;
    return Promise.reject(new Error("Unauthenticated"));
  }

  return res;
}

export async function fetchStatus(): Promise<boolean> {
  const res = await fetch("/api/status", { credentials: "same-origin" });
  const data = await res.json();
  return data.authenticated as boolean;
}

export async function logout(): Promise<void> {
  await apiFetch("/api/auth/logout", { method: "POST" });
}

export interface WeaponsResponse {
  weapons: WeaponDto[];
  cachedAt?: number;
}

export async function fetchWeapons(refresh = false): Promise<WeaponsResponse> {
  const res = await apiFetch(`/api/weapons${refresh ? "?refresh=1" : ""}`);
  if (!res.ok) throw new Error(`Failed to load weapons (${res.status})`);
  return (await res.json()) as WeaponsResponse;
}

export async function fetchPerks(): Promise<WeaponTypePerks[]> {
  const res = await apiFetch("/api/perks");
  if (!res.ok) throw new Error(`Failed to load perks (${res.status})`);
  return (await res.json()).weaponTypes as WeaponTypePerks[];
}

export async function savePerkRating(body: {
  name: string; weaponType: string; rating: string; reason: string; tags: string[]; notes: string;
}): Promise<void> {
  const res = await apiFetch("/api/perks", {
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
  const res = await apiFetch("/api/memberships");
  if (!res.ok) throw new Error(`Failed to load accounts (${res.status})`);
  return res.json();
}

export async function selectMembership(membershipType: number, membershipId: string): Promise<void> {
  const res = await apiFetch("/api/memberships/select", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ membershipType, membershipId }),
  });
  if (!res.ok) throw new Error(`Failed to switch account (${res.status})`);
}

export async function fetchBuilds(): Promise<Record<string, Build>> {
  const res = await apiFetch("/api/builds");
  if (!res.ok) throw new Error(`Failed to load builds (${res.status})`);
  return (await res.json()).builds as Record<string, Build>;
}

export async function saveBuild(key: string, data: Build): Promise<void> {
  const res = await apiFetch("/api/builds", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, data }),
  });
  if (!res.ok) throw new Error(`Failed to save build (${res.status})`);
}

export async function fetchActivities(): Promise<ActivityRec[]> {
  const res = await apiFetch("/api/activities");
  if (!res.ok) throw new Error(`Failed to load activities (${res.status})`);
  return (await res.json()).activities as ActivityRec[];
}

export async function fetchActivityCatalog(): Promise<{ name: string; type: string }[]> {
  const res = await apiFetch("/api/activities/catalog");
  if (!res.ok) throw new Error(`Failed to load activity catalog (${res.status})`);
  return (await res.json()).catalog as { name: string; type: string }[];
}

export async function saveActivity(name: string, data: ActivityRec): Promise<void> {
  const res = await apiFetch("/api/activities", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, data }),
  });
  if (!res.ok) throw new Error(`Failed to save activity (${res.status})`);
}

export async function fetchTags(): Promise<Record<string, string>> {
  const res = await apiFetch("/api/tags");
  if (!res.ok) throw new Error(`Failed to load tags (${res.status})`);
  return (await res.json()).tags as Record<string, string>;
}

export async function saveTag(instanceId: string, tag: string): Promise<void> {
  const res = await apiFetch("/api/tags", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ instanceId, tag }),
  });
  if (!res.ok) throw new Error(`Failed to save tag (${res.status})`);
}

export async function fetchArmor(): Promise<{ armor: ArmorPiece[]; statNames: string[] }> {
  const res = await apiFetch("/api/armor");
  if (!res.ok) throw new Error(`Failed to load armor (${res.status})`);
  return res.json();
}

export async function fetchCounts(): Promise<{
  weapons: number; armor: number; vaultWeapons: number; vaultArmor: number;
}> {
  const res = await apiFetch("/api/counts");
  if (!res.ok) throw new Error(`Failed to load counts (${res.status})`);
  return res.json();
}

export async function fetchCharacters(): Promise<Character[]> {
  const res = await apiFetch("/api/characters");
  if (!res.ok) throw new Error(`Failed to load characters (${res.status})`);
  return (await res.json()).characters as Character[];
}

export async function moveItem(body: {
  instanceId: string; itemHash: number; targetCharacterId: string; equip: boolean;
}): Promise<void> {
  const res = await apiFetch("/api/transfer", {
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
  const res = await apiFetch("/api/transfer/bulk", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items, targetCharacterId, equip }),
  });
  if (!res.ok) throw new Error(`Bulk move failed (${res.status})`);
  return (await res.json()).results as MoveResult[];
}

export async function fetchLoadouts(): Promise<Loadout[]> {
  const res = await apiFetch("/api/loadouts");
  if (!res.ok) throw new Error(`Failed to load loadouts (${res.status})`);
  return (await res.json()).loadouts as Loadout[];
}

export async function saveLoadout(name: string, characterId: string, items: LoadoutItem[]): Promise<void> {
  const res = await apiFetch("/api/loadouts", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, characterId, items }),
  });
  if (!res.ok) throw new Error(`Failed to save loadout (${res.status})`);
}

export async function deleteLoadout(name: string): Promise<void> {
  const res = await apiFetch(`/api/loadouts/${encodeURIComponent(name)}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Failed to delete loadout (${res.status})`);
}

export async function applyLoadout(name: string): Promise<MoveResult[]> {
  const res = await apiFetch("/api/loadouts/apply", {
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
  const res = await apiFetch("/api/postmaster");
  if (!res.ok) throw new Error(`Failed to load postmaster (${res.status})`);
  return (await res.json()).items as PostmasterItem[];
}

export async function pullPostmaster(item: PostmasterItem): Promise<void> {
  const res = await apiFetch("/api/postmaster/pull", {
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

export async function fetchRecommendations(context: string): Promise<Recommendations> {
  const res = await apiFetch(`/api/recommendations?context=${encodeURIComponent(context)}`);
  if (!res.ok) throw new Error(`Failed to load recommendations (${res.status})`);
  return (await res.json()) as Recommendations;
}

export async function fetchLoadoutSuggestion(activity: string): Promise<LoadoutSuggestion> {
  const res = await apiFetch(`/api/loadout-suggestion?activity=${encodeURIComponent(activity)}`);
  if (!res.ok) throw new Error(`Failed to load loadout suggestion (${res.status})`);
  return (await res.json()) as LoadoutSuggestion;
}

export interface Ad {
  offer_id: number;
  headline: string;
  blurb: string;
  cta: string;
  image_url: string | null;
  click_url: string;
}

export async function fetchAds(n = 4): Promise<Ad[]> {
  try {
    const res = await apiFetch("/api/ads?n=" + n);
    if (!res.ok) return [];
    const data = await res.json();
    return (data.ads ?? []) as Ad[];
  } catch {
    return [];
  }
}

export async function fetchArmorSets(): Promise<ArmorSet[]> {
  const res = await apiFetch("/api/armor-sets");
  if (!res.ok) throw new Error(`Failed to load armor sets (${res.status})`);
  return (await res.json()).armorSets as ArmorSet[];
}

export async function saveArmorSet(set: ArmorSet): Promise<void> {
  const res = await apiFetch("/api/armor-sets", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(set),
  });
  if (!res.ok) throw new Error(`Failed to save armor set (${res.status})`);
}

export async function deleteArmorSet(name: string): Promise<void> {
  const res = await apiFetch(`/api/armor-sets/${encodeURIComponent(name)}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Failed to delete armor set (${res.status})`);
}

export async function applyArmorSet(name: string): Promise<MoveResult[]> {
  const res = await apiFetch("/api/armor-sets/apply", {
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

export type DismantleCandidate = {
  instanceId: string;
  itemHash: number;
  name: string;
  icon: string;
  power: number;
  bucketHash: string;
  verdict: string;
  source: "tagged" | "suggested";
  reason: string;
  blocked: "" | "locked" | "exotic" | "high_verdict" | "equipped";
  overridable: boolean;
};

export type BatchPlan = {
  staged: string[];
  deferred: string[];
  perBucket: Record<string, { name: string; free: number; staged: number }>;
};

async function dismantlePost(url: string, body: unknown): Promise<any> {
  const res = await apiFetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(data.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

export async function fetchDismantlePreview(characterId: string): Promise<{
  candidates: DismantleCandidate[];
  plan: BatchPlan;
  staged: Record<string, boolean>;
}> {
  return dismantlePost("/api/dismantle/preview", { characterId });
}

export async function runDismantleSweep(
  characterId: string, instanceIds: string[], overrides: string[],
): Promise<{
  staged: string[];
  deferred: string[];
  rejected: { instanceId: string; reason: string }[];
  failed: { instanceId: string; error: string }[];
}> {
  return dismantlePost("/api/dismantle/sweep", { characterId, instanceIds, overrides });
}

export async function undoDismantleSweep(characterId: string): Promise<{
  restored: string[];
  failed: { instanceId: string; error: string }[];
}> {
  return dismantlePost("/api/dismantle/undo", { characterId });
}

export async function bulkTag(instanceIds: string[], tag: string): Promise<number> {
  const res = await apiFetch("/api/tags/bulk", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ instanceIds, tag }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(data.detail || `Bulk tag failed (${res.status})`);
  }
  return (await res.json()).count as number;
}

export type ChaseRow = {
  itemHash: number;
  name: string;
  icon: string;
  weaponType: string;
  ceiling: string;
  ownedBest: string;
  chasePerks: string[];
  haveCount: number;
};

export async function fetchChase(): Promise<ChaseRow[]> {
  const res = await apiFetch("/api/chase");
  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(data.detail || `Failed to load chase list (${res.status})`);
  }
  return (await res.json()).chase as ChaseRow[];
}

export type OutfitItem = {
  instanceId: string; name: string; icon: string; isExotic: boolean;
  matchedPerks?: string[]; setName?: string; focus?: number;
  setBonuses?: { count: number; name: string; description: string }[];
} | null;

export type Outfit = {
  className: string;
  subclass: string;
  statPriority: string[];
  build: Record<string, unknown>;
  armor: Record<string, OutfitItem>;
  weapons: Record<string, OutfitItem>;
};

export async function fetchOutfits(): Promise<Outfit[]> {
  const res = await apiFetch("/api/outfits");
  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(data.detail || `Failed to load outfits (${res.status})`);
  }
  return (await res.json()).outfits as Outfit[];
}
