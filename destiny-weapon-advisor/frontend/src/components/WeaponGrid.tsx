import { useEffect, useMemo, useState } from "react";
import { fetchCharacters, fetchTags, fetchWeapons, saveTag } from "../api";
import { Character, Verdict, WeaponDto } from "../types";
import { matchWeapon, parseQuery } from "../search";
import { TAGS } from "../visual";
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
  const [characters, setCharacters] = useState<Character[]>([]);
  const [cachedAt, setCachedAt] = useState<number | undefined>();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [selected, setSelected] = useState<WeaponDto | null>(null);
  const [location, setLocation] = useState("All");
  const [tags, setTags] = useState<Record<string, string>>({});
  const [tagFilter, setTagFilter] = useState("all");
  const [filters, setFilters] = useState<FilterState>({
    verdict: "all", weaponType: "all", search: "",
  });

  function setTag(instanceId: string, tag: string) {
    setTags((t) => ({ ...t, [instanceId]: tag }));
    saveTag(instanceId, tag).catch(() => {});
  }

  function load(refresh: boolean) {
    if (refresh) setRefreshing(true);
    setError(null);
    fetchWeapons(refresh)
      .then((r) => { setWeapons(r.weapons); setCachedAt(r.cachedAt); })
      .catch((e) => setError(e.message))
      .finally(() => { setLoading(false); setRefreshing(false); });
  }

  useEffect(() => {
    load(false);
    fetchCharacters().then(setCharacters).catch(() => setCharacters([]));
    fetchTags().then(setTags).catch(() => setTags({}));
  }, []);

  const types = useMemo(
    () => Array.from(new Set(weapons.map((w) => w.weaponType))).sort(),
    [weapons],
  );

  const tabs = useMemo(
    () => ["All", ...characters.map((c) => c.className), "Vault"],
    [characters],
  );

  const terms = useMemo(() => parseQuery(filters.search), [filters.search]);

  const shown = useMemo(() => {
    return weapons
      .filter((w) => location === "All" || w.location === location)
      .filter((w) => tagFilter === "all" || (tags[w.instanceId] || "") === tagFilter)
      .filter((w) => filters.verdict === "all" || w.verdict === filters.verdict)
      .filter((w) => filters.weaponType === "all" || w.weaponType === filters.weaponType)
      .filter((w) => matchWeapon(w, tags[w.instanceId] || "", terms))
      .sort((a, b) => ORDER[a.verdict] - ORDER[b.verdict] || a.name.localeCompare(b.name));
  }, [weapons, filters, location, tags, tagFilter, terms]);

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
      <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
        {tabs.map((t) => {
          const ch = characters.find((c) => c.className === t);
          const active = t === location;
          return (
            <button
              key={t}
              onClick={() => setLocation(t)}
              style={{
                padding: "6px 14px", borderRadius: 6, cursor: "pointer",
                border: "1px solid #d0d7de",
                background: active ? "#1b2838" : "#fff",
                color: active ? "#fff" : "#333", fontWeight: active ? 700 : 400,
              }}
            >
              {t}{ch ? ` ✦${ch.light}` : ""}
            </button>
          );
        })}
      </div>
      <div style={{ marginBottom: 8 }}>
        <select value={tagFilter} onChange={(e) => setTagFilter(e.target.value)}>
          <option value="all">All tags</option>
          <option value="">Untagged</option>
          {TAGS.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>
      <Filters state={filters} types={types} onChange={setFilters} />
      {selected && (
        <WeaponDetail
          w={selected}
          characters={characters}
          tag={tags[selected.instanceId] || ""}
          onTag={(t) => setTag(selected.instanceId, t)}
          onClose={() => setSelected(null)}
          onMoved={() => { load(false); setSelected(null); }}
        />
      )}
      <p style={{ color: "#666" }}>{shown.length} of {weapons.length} weapons</p>
      {shown.length === 0 && (
        <p style={{ color: "#999" }}>No weapons match your current tab/filters.</p>
      )}
      <div
        style={{
          display: "grid", gap: 8,
          gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
        }}
      >
        {shown.map((w) => (
          <WeaponCard key={w.instanceId} w={w} tag={tags[w.instanceId]} onClick={() => setSelected(w)} />
        ))}
      </div>
    </div>
  );
}
