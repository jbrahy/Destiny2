import { useEffect, useMemo, useState } from "react";
import { fetchArmor, fetchCharacters, fetchTags, moveItem, saveTag } from "../api";
import { ArmorPiece, Character } from "../types";
import { matchArmor, parseQuery } from "../search";
import { TAGS } from "../visual";
import { Icon } from "./Icon";
import { TagChip, TagSelect } from "./TagSelect";

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
        <span style={{ color: "var(--muted)", fontSize: 12 }}>(by total stats vs your best in this slot)</span>
      </p>
      <h3 style={{ margin: "8px 0 6px" }}>Stats (total {total(a)})</h3>
      {Object.entries(a.stats).map(([name, value]) => (
        <div key={name} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
          <span style={{ width: 90, fontSize: 12, color: "var(--muted)" }}>{name}</span>
          <div style={{ flex: 1, background: "var(--track)", borderRadius: 3, height: 10 }}>
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
  const [tags, setTags] = useState<Record<string, string>>({});
  const [tagFilter, setTagFilter] = useState("all");
  const [selected, setSelected] = useState<ArmorPiece | null>(null);
  const [equip, setEquip] = useState(false);
  const [moving, setMoving] = useState(false);
  const [moveMsg, setMoveMsg] = useState<string | null>(null);

  function load() {
    return Promise.all([fetchArmor(), fetchCharacters()])
      .then(([a, c]) => { setArmor(a.armor); setCharacters(c); })
      .catch((e) => setError(e.message));
  }

  function setTag(instanceId: string, tag: string) {
    setTags((t) => ({ ...t, [instanceId]: tag }));
    saveTag(instanceId, tag).catch(() => {});
  }

  useEffect(() => {
    load().finally(() => setLoading(false));
    fetchTags().then(setTags).catch(() => setTags({}));
  }, []);
  useEffect(() => { setMoveMsg(null); }, [selected]);

  async function doMove(target: Character) {
    if (!selected) return;
    const ok = window.confirm(
      `Move "${selected.name}" to your ${target.className}${equip ? " and equip it" : ""}?`,
    );
    if (!ok) return;
    setMoving(true);
    setMoveMsg(null);
    try {
      await moveItem({
        instanceId: selected.instanceId, itemHash: selected.itemHash,
        targetCharacterId: target.id, equip,
      });
      await load();
      setSelected(null);
    } catch (e) {
      setMoveMsg(`✗ ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setMoving(false);
    }
  }

  const maxBySlot = useMemo(() => {
    const m: Record<string, number> = {};
    for (const a of armor) m[a.slot] = Math.max(m[a.slot] || 0, total(a));
    return m;
  }, [armor]);

  const tabs = useMemo(() => ["All", ...characters.map((c) => c.className), "Vault"], [characters]);

  const terms = useMemo(() => parseQuery(search), [search]);

  const shown = useMemo(
    () =>
      armor
        .map((a) => ({ a, r: rate(a, maxBySlot[a.slot] || 0) }))
        .filter(({ a }) => location === "All" || a.location === location)
        .filter(({ a }) => slot === "all" || a.slot === slot)
        .filter(({ r }) => ratingFilter === "all" || r.label === ratingFilter)
        .filter(({ a }) => tagFilter === "all" || (tags[a.instanceId] || "") === tagFilter)
        .filter(({ a, r }) => matchArmor(a, tags[a.instanceId] || "", r.label, terms))
        .sort((x, y) =>
          SLOTS.indexOf(x.a.slot) - SLOTS.indexOf(y.a.slot) || total(y.a) - total(x.a)),
    [armor, maxBySlot, location, slot, ratingFilter, tags, tagFilter, terms],
  );

  if (loading) return <div>Loading armor…</div>;
  if (error) return <div style={{ color: "#c62828" }}>Error: {error}</div>;
  if (armor.length === 0)
    return (
      <div style={{ color: "var(--muted)" }}>
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
                padding: "6px 14px", borderRadius: 6, cursor: "pointer", border: "1px solid var(--border)",
                background: active ? "var(--accent)" : "var(--panel2)", color: active ? "#0a0e16" : "var(--text)",
                fontWeight: active ? 700 : 400,
              }}
            >
              {t}{ch ? ` ✦${ch.light}` : ""}
            </button>
          );
        })}
      </div>
      <div style={{ display: "flex", gap: 12, marginBottom: 12, flexWrap: "wrap" }}>
        <input placeholder="Search… e.g. is:exotic slot:helmet rating:top" value={search}
          onChange={(e) => setSearch(e.target.value)} style={{ minWidth: 260 }} />
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
        <select value={tagFilter} onChange={(e) => setTagFilter(e.target.value)}>
          <option value="all">All tags</option>
          <option value="">Untagged</option>
          {TAGS.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>
      {selected && (
        <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 16, marginBottom: 16 }}>
          <button onClick={() => setSelected(null)} style={{ float: "right" }}>Close</button>
          <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 8 }}>
            <Icon path={selected.icon} size={56} alt={selected.name}
              border={selected.isExotic ? "#caa000" : undefined} />
            <div>
              <h2 style={{ margin: "0 0 2px" }}>
                {selected.name} {selected.isExotic && <span style={{ color: "#caa000" }}>◆</span>}
              </h2>
              <p style={{ margin: 0, color: "var(--muted)" }}>
                {selected.slot} · {selected.className} · {selected.location} · ✦{selected.power}
                {selected.isMasterworked ? " · ★ Masterworked" : ""}
              </p>
            </div>
          </div>
          <div style={{ marginBottom: 10 }}>
            <strong style={{ fontSize: 13, marginRight: 6 }}>Tag:</strong>
            <TagSelect value={tags[selected.instanceId] || ""} onChange={(t) => setTag(selected.instanceId, t)} />
          </div>
          {characters.length > 0 && (
            <div style={{ background: "var(--panel2)", borderRadius: 6, padding: "8px 10px", marginBottom: 10 }}>
              <strong style={{ fontSize: 13 }}>Move to: </strong>
              {characters
                .filter((c) => selected.className === "Any" || c.className === selected.className)
                .map((c) => (
                  <button
                    key={c.id}
                    disabled={moving || selected.location === c.className}
                    onClick={() => doMove(c)}
                    style={{ margin: "0 4px", padding: "4px 10px" }}
                  >
                    {c.className} {c.current ? "(current)" : ""}
                  </button>
                ))}
              <label style={{ marginLeft: 8, fontSize: 13 }}>
                <input type="checkbox" checked={equip} onChange={(e) => setEquip(e.target.checked)} /> equip
              </label>
              {moveMsg && (
                <div style={{ marginTop: 6, fontSize: 13, color: moveMsg.startsWith("✓") ? "#2e7d32" : "#c62828" }}>
                  {moveMsg}
                </div>
              )}
            </div>
          )}
          <ArmorDetail a={selected} rating={rate(selected, maxBySlot[selected.slot] || 0)} />
        </div>
      )}
      <p style={{ color: "var(--muted)" }}>{shown.length} of {armor.length} pieces</p>
      {shown.length === 0 && (
        <p style={{ color: "var(--muted)" }}>No armor matches your current tab/filters.</p>
      )}
      <div style={{
        display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
      }}>
        {shown.map(({ a, r }) => (
          <div
            key={a.instanceId}
            onClick={() => setSelected(a)}
            style={{
              display: "flex", gap: 10, alignItems: "flex-start", background: "var(--panel)",
              border: "1px solid var(--border)", borderRadius: 8, padding: 10, cursor: "pointer",
              borderLeft: `6px solid ${r.color}`,
            }}
          >
            <Icon path={a.icon} size={44} alt={a.name} border={a.isExotic ? "#caa000" : undefined} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <strong style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {a.name}{a.isExotic ? " ◆" : ""}
                </strong>
                <span style={{ display: "flex", gap: 6, alignItems: "center", whiteSpace: "nowrap" }}>
                  <TagChip tag={tags[a.instanceId]} />
                  <span style={{ color: r.color, fontWeight: 600 }}>{r.label}</span>
                </span>
              </div>
              <div style={{ fontSize: 12, color: "var(--muted)" }}>
                {a.slot} · {a.location}{a.isMasterworked ? " · ★" : ""} · ✦{a.power}
                {a.equipped && <span style={{ color: "#2e7d32", fontWeight: 600 }}> · equipped</span>}
              </div>
              <div style={{ fontSize: 12, color: "var(--text)", marginTop: 2 }}>Total {total(a)}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
