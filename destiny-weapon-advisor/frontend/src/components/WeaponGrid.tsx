import { useEffect, useMemo, useState } from "react";
import { bulkMove, fetchCharacters, fetchTags, fetchWeapons, saveTag } from "../api";
import { Character, Verdict, WeaponDto } from "../types";
import { matchWeapon, parseQuery } from "../search";
import { TAGS } from "../visual";
import { ComparePanel } from "./ComparePanel";
import { FilterState, Filters, SortKey } from "./Filters";
import { WeaponCard } from "./WeaponCard";
import { WeaponDetail } from "./WeaponDetail";

const ORDER: Record<Verdict, number> = {
  god_roll: 0, masterwork: 1, good: 2, no_data: 3, dismantle: 4,
};

function compareWeapons(a: WeaponDto, b: WeaponDto, sort: SortKey): number {
  switch (sort) {
    case "power_asc":
      return a.power - b.power || a.name.localeCompare(b.name);
    case "verdict":
      return ORDER[a.verdict] - ORDER[b.verdict] || a.name.localeCompare(b.name);
    case "name":
      return a.name.localeCompare(b.name);
    case "type":
      return a.weaponType.localeCompare(b.weaponType) || b.power - a.power;
    case "element":
      return a.element.localeCompare(b.element) || b.power - a.power;
    case "power_desc":
    default:
      return b.power - a.power || a.name.localeCompare(b.name);
  }
}

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
    verdict: "all", weaponType: "all", element: "all", search: "", sort: "power_desc",
  });

  const [bulkBusy, setBulkBusy] = useState(false);
  const [compare, setCompare] = useState<WeaponDto[]>([]);

  function toggleCompare(w: WeaponDto) {
    setCompare((c) =>
      c.some((x) => x.instanceId === w.instanceId)
        ? c.filter((x) => x.instanceId !== w.instanceId)
        : c.length < 4 ? [...c, w] : c);
  }

  function setTag(instanceId: string, tag: string) {
    setTags((t) => ({ ...t, [instanceId]: tag }));
    saveTag(instanceId, tag).catch(() => {});
  }

  async function bulkMoveTo(target: string, label: string) {
    if (shown.length === 0) return;
    if (!window.confirm(`Move all ${shown.length} shown weapons to ${label}? (equipped items are skipped)`)) return;
    setBulkBusy(true);
    try {
      await bulkMove(shown.map((w) => ({ instanceId: w.instanceId, itemHash: w.itemHash })), target, false);
      load(false);
    } finally {
      setBulkBusy(false);
    }
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

  // Only damage types actually present, in Destiny's canonical order rather
  // than alphabetical — a subclass-shaped list reads faster than A-Z.
  const elements = useMemo(() => {
    const order = ["Kinetic", "Arc", "Solar", "Void", "Stasis", "Strand"];
    const present = new Set(weapons.map((w) => w.element));
    return [
      ...order.filter((e) => present.has(e)),
      ...Array.from(present).filter((e) => !order.includes(e)).sort(),
    ];
  }, [weapons]);

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
      .filter((w) => filters.element === "all" || w.element === filters.element)
      .filter((w) => matchWeapon(w, tags[w.instanceId] || "", terms))
      .sort((a, b) => compareWeapons(a, b, filters.sort));
  }, [weapons, filters, location, tags, tagFilter, terms]);

  if (loading) return <div>Analyzing your inventory… (first run downloads the manifest)</div>;
  if (error) return <div style={{ color: "#c62828" }}>Error: {error}</div>;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
        <button onClick={() => load(true)} disabled={refreshing}>
          {refreshing ? "Refreshing…" : "↻ Refresh"}
        </button>
        <span style={{ color: "var(--muted)", fontSize: 13 }}>
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
                border: "1px solid var(--border)",
                background: active ? "var(--accent)" : "var(--panel2)",
                color: active ? "#0a0e16" : "var(--text)", fontWeight: active ? 700 : 400,
              }}
            >
              {t}{ch ? ` ✦${ch.light}` : ""}
            </button>
          );
        })}
      </div>
      {characters.length > 0 && shown.length > 0 && (
        <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 8, fontSize: 13 }}>
          <span style={{ color: "var(--muted)" }}>Move all {shown.length} shown to:</span>
          {characters.map((c) => (
            <button key={c.id} disabled={bulkBusy} onClick={() => bulkMoveTo(c.id, c.className)}
              style={{ padding: "2px 8px" }}>{c.className}</button>
          ))}
          <button disabled={bulkBusy} onClick={() => bulkMoveTo("vault", "Vault")}
            style={{ padding: "2px 8px" }}>Vault</button>
          {bulkBusy && <span style={{ color: "var(--muted)" }}>moving…</span>}
        </div>
      )}
      <div style={{ marginBottom: 8 }}>
        <select value={tagFilter} onChange={(e) => setTagFilter(e.target.value)}>
          <option value="all">All tags</option>
          <option value="">Untagged</option>
          {TAGS.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>
      <Filters state={filters} types={types} elements={elements} onChange={setFilters} />
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
      <ComparePanel
        items={compare}
        onRemove={(id) => setCompare((c) => c.filter((x) => x.instanceId !== id))}
        onClear={() => setCompare([])}
      />
      <p style={{ color: "var(--muted)" }}>
        {shown.length} of {weapons.length} weapons
        {compare.length === 1 && <span style={{ color: "var(--accent)" }}> · pick another ⇄ to compare</span>}
      </p>
      {shown.length === 0 && (
        <p style={{ color: "var(--muted)" }}>No weapons match your current tab/filters.</p>
      )}
      <div
        style={{
          display: "grid", gap: 8,
          gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
        }}
      >
        {shown.map((w) => (
          <WeaponCard
            key={w.instanceId}
            w={w}
            tag={tags[w.instanceId]}
            comparing={compare.some((x) => x.instanceId === w.instanceId)}
            onToggleCompare={() => toggleCompare(w)}
            onClick={() => setSelected(w)}
          />
        ))}
      </div>
    </div>
  );
}
