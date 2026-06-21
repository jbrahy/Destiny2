import { useEffect, useMemo, useState } from "react";
import { fetchWeapons } from "../api";
import { Verdict, WeaponDto } from "../types";
import { FilterState, Filters } from "./Filters";
import { WeaponCard } from "./WeaponCard";
import { WeaponDetail } from "./WeaponDetail";

const ORDER: Record<Verdict, number> = {
  god_roll: 0, upgrade: 1, good: 2, no_data: 3, dismantle: 4,
};

export function WeaponGrid() {
  const [weapons, setWeapons] = useState<WeaponDto[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<WeaponDto | null>(null);
  const [filters, setFilters] = useState<FilterState>({
    verdict: "all", weaponType: "all", search: "",
  });

  useEffect(() => {
    fetchWeapons()
      .then(setWeapons)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

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
