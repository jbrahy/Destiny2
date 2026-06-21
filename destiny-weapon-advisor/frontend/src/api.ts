import { WeaponDto } from "./types";

export const loginUrl = "/api/login";

export async function fetchStatus(): Promise<boolean> {
  const res = await fetch("/api/status");
  const data = await res.json();
  return data.authenticated as boolean;
}

export async function fetchWeapons(): Promise<WeaponDto[]> {
  const res = await fetch("/api/weapons");
  if (!res.ok) throw new Error(`Failed to load weapons (${res.status})`);
  const data = await res.json();
  return data.weapons as WeaponDto[];
}
