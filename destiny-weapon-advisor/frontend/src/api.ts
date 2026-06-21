import { WeaponDto } from "./types";

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
