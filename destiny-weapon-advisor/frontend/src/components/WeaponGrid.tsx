import { useEffect, useMemo, useState } from "react";
import { fetchWeapons } from "../api";
import { Verdict, WeaponDto } from "../types";
import { FilterState, Filters } from "./Filters";
import { WeaponCard } from "./WeaponCard";
import { WeaponDetail } from "./WeaponDetail";

const ORDER: Record<Verdict, number> = {
  god_roll: 0, upgrade: 1, good: 2, no_data: 3, dismantle: 4,
};

function sinceText(cachedAt?: number): string {
  if (!cachedAt) return "";
  const secs = Math.max(0, Date.now() / 1000 - cachedAt);
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)} min ago`;
  return `${Math.floor(secs / 3600)} hr ago`;
}

export function WeaponGrid() {
  const [weapons, setWeapons] = useState<WeaponDto[]>([]);
  const [cachedAt, setCachedAt] = useState<number | undefined>();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [selected, setSelected] = useState<WeaponDto | null>(null);
  const [filters, setFilters] = useState<FilterState>({
    verdict: "all", weaponType: "all", search: "",
  });

  function load(refresh: boolean) {
    if (refresh) setRefreshing(true);
    setError(null);
    fetchWeapons(refresh)
      .then((r) => { setWeapons(r.weapons); setCachedAt(r.cachedAt); })
      .catch((e) => setError(e.message))
      .finally(() => { setLoading(false); setRefreshing(false); });
  }

  useEffect(() => { load(false); }, []);

  const types = useMemo(
    () => Array.from(new Set(weapons.map((w) => w.weaponType))).sort(),
    [weapons],
  );

  const shown = useMemo(() => {
    return weapons
      .filter((w) => filters.verdict === "all" || w.verdict === filters.verdict)
      .filter((w) => filters.weaponType === "all" || w.weaponType === filters.weaponType)
      .filter((w) => w.name.toLowerCase().includes(filters.search.toLowerCase()))
      .sort((a, b) => ORDER[a.verdict] - ORDER[b.verdict] || a.name.localeCompare(b.name));
  }, [weapons, filters]);

  if (loading) return <div>Analyzing your inventory… (first run downloads the manifest)</div>;
  if (error) return <div style={{ color: "#c62828" }}>Error: {error}</div>;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
        <button onClick={() => load(true)} disabled={refreshing}>
          {refreshing ? "Refreshing…" : "↻ Refresh"}
        </button>
        <span style={{ color: "#888", fontSize: 13 }}>
          {cachedAt ? `Last refreshed ${sinceText(cachedAt)}` : "Showing cached data"}
        </span>
      </div>
      <Filters state={filters} types={types} onChange={setFilters} />
      {selected && <WeaponDetail w={selected} onClose={() => setSelected(null)} />}
      <p style={{ color: "#666" }}>{shown.length} of {weapons.length} weapons</p>
      <div
        style={{
          display: "grid", gap: 8,
          gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
        }}
      >
        {shown.map((w) => (
          <WeaponCard key={w.instanceId} w={w} onClick={() => setSelected(w)} />
        ))}
      </div>
    </div>
  );
}
