import { useEffect, useMemo, useState } from "react";
import { fetchArmor, fetchCharacters } from "../api";
import { ArmorPiece, Character } from "../types";

const SLOTS = ["Helmet", "Gauntlets", "Chest Armor", "Leg Armor", "Class Item"];

function ArmorDetail({ a, onClose }: { a: ArmorPiece; onClose: () => void }) {
  const total = Object.values(a.stats).reduce((x, y) => x + y, 0);
  return (
    <div style={{ border: "1px solid #ccc", borderRadius: 8, padding: 16, marginBottom: 16 }}>
      <button onClick={onClose} style={{ float: "right" }}>Close</button>
      <h2 style={{ margin: "0 0 4px" }}>
        {a.name} {a.isExotic && <span style={{ color: "#caa000" }}>◆</span>}
      </h2>
      <p style={{ margin: "0 0 8px", color: "#666" }}>
        {a.slot} · {a.className} · {a.location} · ✦{a.power}
        {a.isMasterworked ? " · ★ Masterworked" : ""}
      </p>
      <h3 style={{ margin: "8px 0 6px" }}>Stats (total {total})</h3>
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
    </div>
  );
}

export function ArmorList() {
  const [armor, setArmor] = useState<ArmorPiece[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [location, setLocation] = useState("All");
  const [slot, setSlot] = useState("all");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<ArmorPiece | null>(null);

  useEffect(() => {
    Promise.all([fetchArmor(), fetchCharacters()])
      .then(([a, c]) => { setArmor(a.armor); setCharacters(c); })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const tabs = useMemo(() => ["All", ...characters.map((c) => c.className), "Vault"], [characters]);

  const shown = useMemo(
    () =>
      armor
        .filter((a) => location === "All" || a.location === location)
        .filter((a) => slot === "all" || a.slot === slot)
        .filter((a) => a.name.toLowerCase().includes(search.toLowerCase()))
        .sort((a, b) => SLOTS.indexOf(a.slot) - SLOTS.indexOf(b.slot) || b.power - a.power),
    [armor, location, slot, search],
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
        <select value={slot} onChange={(e) => setSlot(e.target.value)}>
          <option value="all">All slots</option>
          {SLOTS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      {selected && <ArmorDetail a={selected} onClose={() => setSelected(null)} />}
      <p style={{ color: "#666" }}>{shown.length} of {armor.length} pieces</p>
      <div style={{
        display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
      }}>
        {shown.map((a) => (
          <div
            key={a.instanceId}
            onClick={() => setSelected(a)}
            style={{
              border: "1px solid #ddd", borderRadius: 8, padding: 12, cursor: "pointer",
              borderLeft: `6px solid ${a.isExotic ? "#caa000" : "#888"}`,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
              <strong>{a.name}{a.isExotic ? " ◆" : ""}</strong>
              <span style={{ fontWeight: 600, whiteSpace: "nowrap" }}>✦{a.power}</span>
            </div>
            <div style={{ fontSize: 12, color: "#666" }}>
              {a.slot} · {a.location}{a.isMasterworked ? " · ★" : ""}
            </div>
            <div style={{ fontSize: 12, color: "#333", marginTop: 2 }}>
              Total {Object.values(a.stats).reduce((x, y) => x + y, 0)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
