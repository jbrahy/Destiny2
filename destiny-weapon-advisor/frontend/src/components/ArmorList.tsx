import { useEffect, useMemo, useState } from "react";
import { fetchArmor, fetchCharacters } from "../api";
import { ArmorPiece, Character } from "../types";

const SLOTS = ["Helmet", "Gauntlets", "Chest Armor", "Leg Armor", "Class Item"];

function total(a: ArmorPiece): number {
  return Object.values(a.stats).reduce((x, y) => x + y, 0);
}

interface Rating {
  label: string;
  color: string;
  rank: number; // lower = better, for sorting
}

// Objective rating: exotics are always keepers; everything else is judged by its
// total stat roll relative to your best piece in the same slot.
function rate(a: ArmorPiece, maxInSlot: number): Rating {
  if (a.isExotic) return { label: "Exotic", color: "#caa000", rank: 0 };
  const pct = maxInSlot > 0 ? total(a) / maxInSlot : 0;
  if (pct >= 0.92) return { label: "Top Roll", color: "#2e7d32", rank: 1 };
  if (pct >= 0.8) return { label: "Good", color: "#1565c0", rank: 2 };
  if (pct >= 0.65) return { label: "OK", color: "#f9a825", rank: 3 };
  return { label: "Dismantle?", color: "#c62828", rank: 4 };
}

function ArmorDetail({ a, rating }: { a: ArmorPiece; rating: Rating }) {
  return (
    <>
      <p style={{ margin: "0 0 4px" }}>
        <strong>Rating:</strong>{" "}
        <span style={{ color: rating.color, fontWeight: 600 }}>{rating.label}</span>{" "}
        <span style={{ color: "#888", fontSize: 12 }}>(by total stats vs your best in this slot)</span>
      </p>
      <h3 style={{ margin: "8px 0 6px" }}>Stats (total {total(a)})</h3>
      {Object.entries(a.stats).map(([name, value]) => (
        <div key={name} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
          <span style={{ width: 90, fontSize: 12, color: "#555" }}>{name}</span>
          <div style={{ flex: 1, background: "#eee", borderRadius: 3, height: 10 }}>
            <div style={{
              width: `${Math.min(100, (value / 50) * 100)}%`,
              background: "#1565c0", height: 10, borderRadius: 3,
            }} />
          </div>
          <span style={{ width: 32, textAlign: "right", fontSize: 12 }}>{value}</span>
        </div>
      ))}
    </>
  );
}

export function ArmorList() {
  const [armor, setArmor] = useState<ArmorPiece[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [location, setLocation] = useState("All");
  const [slot, setSlot] = useState("all");
  const [ratingFilter, setRatingFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<ArmorPiece | null>(null);

  useEffect(() => {
    Promise.all([fetchArmor(), fetchCharacters()])
      .then(([a, c]) => { setArmor(a.armor); setCharacters(c); })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const maxBySlot = useMemo(() => {
    const m: Record<string, number> = {};
    for (const a of armor) m[a.slot] = Math.max(m[a.slot] || 0, total(a));
    return m;
  }, [armor]);

  const tabs = useMemo(() => ["All", ...characters.map((c) => c.className), "Vault"], [characters]);

  const shown = useMemo(
    () =>
      armor
        .map((a) => ({ a, r: rate(a, maxBySlot[a.slot] || 0) }))
        .filter(({ a }) => location === "All" || a.location === location)
        .filter(({ a }) => slot === "all" || a.slot === slot)
        .filter(({ r }) => ratingFilter === "all" || r.label === ratingFilter)
        .filter(({ a }) => a.name.toLowerCase().includes(search.toLowerCase()))
        .sort((x, y) =>
          SLOTS.indexOf(x.a.slot) - SLOTS.indexOf(y.a.slot) || total(y.a) - total(x.a)),
    [armor, maxBySlot, location, slot, ratingFilter, search],
  );

  if (loading) return <div>Loading armor…</div>;
  if (error) return <div style={{ color: "#c62828" }}>Error: {error}</div>;
  if (armor.length === 0)
    return (
      <div style={{ color: "#666" }}>
        No armor yet — open the <strong>Weapons</strong> tab and <strong>Refresh</strong> first.
      </div>
    );

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Your Armor</h1>
      <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
        {tabs.map((t) => {
          const ch = characters.find((c) => c.className === t);
          const active = t === location;
          return (
            <button
              key={t}
              onClick={() => setLocation(t)}
              style={{
                padding: "6px 14px", borderRadius: 6, cursor: "pointer", border: "1px solid #d0d7de",
                background: active ? "#1b2838" : "#fff", color: active ? "#fff" : "#333",
                fontWeight: active ? 700 : 400,
              }}
            >
              {t}{ch ? ` ✦${ch.light}` : ""}
            </button>
          );
        })}
      </div>
      <div style={{ display: "flex", gap: 12, marginBottom: 12, flexWrap: "wrap" }}>
        <input placeholder="Search name…" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select value={ratingFilter} onChange={(e) => setRatingFilter(e.target.value)}>
          <option value="all">All ratings</option>
          <option value="Exotic">Exotic</option>
          <option value="Top Roll">Top Roll</option>
          <option value="Good">Good</option>
          <option value="OK">OK</option>
          <option value="Dismantle?">Dismantle?</option>
        </select>
        <select value={slot} onChange={(e) => setSlot(e.target.value)}>
          <option value="all">All slots</option>
          {SLOTS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      {selected && (
        <div style={{ border: "1px solid #ccc", borderRadius: 8, padding: 16, marginBottom: 16 }}>
          <button onClick={() => setSelected(null)} style={{ float: "right" }}>Close</button>
          <h2 style={{ margin: "0 0 4px" }}>
            {selected.name} {selected.isExotic && <span style={{ color: "#caa000" }}>◆</span>}
          </h2>
          <p style={{ margin: "0 0 8px", color: "#666" }}>
            {selected.slot} · {selected.className} · {selected.location} · ✦{selected.power}
            {selected.isMasterworked ? " · ★ Masterworked" : ""}
          </p>
          <ArmorDetail a={selected} rating={rate(selected, maxBySlot[selected.slot] || 0)} />
        </div>
      )}
      <p style={{ color: "#666" }}>{shown.length} of {armor.length} pieces</p>
      <div style={{
        display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
      }}>
        {shown.map(({ a, r }) => (
          <div
            key={a.instanceId}
            onClick={() => setSelected(a)}
            style={{
              border: "1px solid #ddd", borderRadius: 8, padding: 12, cursor: "pointer",
              borderLeft: `6px solid ${r.color}`,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
              <strong>{a.name}{a.isExotic ? " ◆" : ""}</strong>
              <span style={{ color: r.color, fontWeight: 600, whiteSpace: "nowrap" }}>{r.label}</span>
            </div>
            <div style={{ fontSize: 12, color: "#666" }}>
              {a.slot} · {a.location}{a.isMasterworked ? " · ★" : ""} · ✦{a.power}
            </div>
            <div style={{ fontSize: 12, color: "#333", marginTop: 2 }}>Total {total(a)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
