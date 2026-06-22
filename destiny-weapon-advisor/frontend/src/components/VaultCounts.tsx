import { useEffect, useState } from "react";
import { fetchCounts } from "../api";

export function VaultCounts() {
  const [c, setC] = useState<{ weapons: number; armor: number; vaultWeapons: number; vaultArmor: number } | null>(null);
  useEffect(() => { fetchCounts().then(setC).catch(() => {}); }, []);
  if (!c) return null;
  return (
    <span style={{ fontSize: 12, color: "#9fb0c0", marginLeft: 16 }}>
      Vault {c.vaultWeapons + c.vaultArmor} · {c.weapons}W / {c.armor}A
    </span>
  );
}
