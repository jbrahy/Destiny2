import { WeaponDto, WeaponTypePerks } from "./types";

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
  name: string; weaponType: string; rating: string; reason: string; tags: string[];
}): Promise<void> {
  const res = await fetch("/api/perks", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Failed to save rating (${res.status})`);
}
