import { useEffect, useState } from "react";
import { fetchBuilds, saveBuild } from "../api";
import { Build } from "../types";
import { ArmorPage } from "./ArmorPage";

const CLASSES = ["Titan", "Hunter", "Warlock"];
const SUBCLASSES = ["Solar", "Arc", "Void", "Stasis", "Strand", "Prismatic"];
const FIELDS: [string, string][] = [
  ["super", "Super"],
  ["aspects", "Aspects"],
  ["fragments", "Fragments"],
  ["grenade", "Grenade"],
  ["melee", "Melee"],
  ["classAbility", "Class Ability"],
  ["movement", "Movement"],
  ["exoticArmor", "Exotic Armor"],
  ["weapons", "Weapons"],
  ["playstyle", "Why / Playstyle"],
];
const LONG = new Set(["fragments", "weapons", "playstyle"]);

function tabStyle(active: boolean) {
  return {
    padding: "6px 14px", borderRadius: 6, cursor: "pointer", border: "1px solid #d0d7de",
    background: active ? "#1b2838" : "#fff", color: active ? "#fff" : "#333",
    fontWeight: active ? 700 : 400,
  } as const;
}

export function BuildsPage() {
  const [builds, setBuilds] = useState<Record<string, Build>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cls, setCls] = useState("Hunter");
  const [subclass, setSubclass] = useState("Solar");
  const [draft, setDraft] = useState<Build>({});
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);

  const key = `${cls}|${subclass}`;

  useEffect(() => {
    fetchBuilds().then(setBuilds).catch((e) => setError(e.message)).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    setDraft(builds[key] || {});
    setDirty(false);
    setSaved(false);
  }, [key, builds]);

  function set(field: string, value: string) {
    setDraft((d) => ({ ...d, [field]: value }));
    setDirty(true);
    setSaved(false);
  }

  async function save() {
    try {
      await saveBuild(key, draft);
      setBuilds((b) => ({ ...b, [key]: draft }));
      setDirty(false);
      setSaved(true);
    } catch (e) {
      setError(String(e));
    }
  }

  if (loading) return <div>Loading builds…</div>;
  if (error) return <div style={{ color: "#c62828" }}>Error: {error}</div>;

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Builds</h1>
      <p style={{ color: "#666", maxWidth: 760 }}>
        A starting build for each class + subclass, seeded from general knowledge.{" "}
        <em>Verify against the current season</em> and edit to taste — your edits are saved locally.
        The armor optimizer below picks the best gear for the stats this build wants.
      </p>

      <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
        {CLASSES.map((c) => (
          <button key={c} onClick={() => setCls(c)} style={tabStyle(c === cls)}>{c}</button>
        ))}
      </div>
      <div style={{ display: "flex", gap: 6, marginBottom: 16, flexWrap: "wrap" }}>
        {SUBCLASSES.map((s) => (
          <button key={s} onClick={() => setSubclass(s)} style={tabStyle(s === subclass)}>{s}</button>
        ))}
      </div>

      <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 16, marginBottom: 28, maxWidth: 760 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <h2 style={{ margin: 0 }}>{cls} · {subclass}</h2>
          <button onClick={save} disabled={!dirty} style={{ padding: "4px 16px" }}>
            {dirty ? "Save" : saved ? "Saved ✓" : "Saved"}
          </button>
        </div>
        {FIELDS.map(([field, label]) => (
          <div key={field} style={{ marginBottom: 8 }}>
            <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#555", marginBottom: 2 }}>
              {label}
            </label>
            {LONG.has(field) ? (
              <textarea
                value={draft[field] || ""}
                onChange={(e) => set(field, e.target.value)}
                rows={2}
                style={{ width: "100%", padding: 6, boxSizing: "border-box" }}
              />
            ) : (
              <input
                value={draft[field] || ""}
                onChange={(e) => set(field, e.target.value)}
                style={{ width: "100%", padding: 6, boxSizing: "border-box" }}
              />
            )}
          </div>
        ))}
      </div>

      <h2 style={{ marginTop: 0 }}>Armor optimizer</h2>
      <ArmorPage />
    </div>
  );
}
