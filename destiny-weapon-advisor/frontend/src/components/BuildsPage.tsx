import { useEffect, useMemo, useState } from "react";
import { fetchBuilds, fetchWeapons, saveBuild } from "../api";
import { Build, WeaponDto } from "../types";
import { ArmorPage } from "./ArmorPage";
import { Icon } from "./Icon";
import { elementColor } from "../visual";

// Subclass element → matching weapon element ("" = Prismatic / no constraint).
const SUBCLASS_ELEMENT: Record<string, string> = {
  Solar: "Solar", Arc: "Arc", Void: "Void", Stasis: "Stasis", Strand: "Strand", Prismatic: "",
};
const VERDICT_RANK: Record<string, number> = { god_roll: 0, upgrade: 1, good: 2 };

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
    padding: "6px 14px", borderRadius: 6, cursor: "pointer", border: "1px solid var(--border)",
    background: active ? "var(--accent)" : "var(--panel2)", color: active ? "#0a0e16" : "var(--text)",
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
  const [weapons, setWeapons] = useState<WeaponDto[]>([]);

  const key = `${cls}|${subclass}`;

  useEffect(() => {
    fetchBuilds().then(setBuilds).catch((e) => setError(e.message)).finally(() => setLoading(false));
    fetchWeapons().then((r) => setWeapons(r.weapons)).catch(() => setWeapons([]));
  }, []);

  const bestWeapons = useMemo(() => {
    const el = SUBCLASS_ELEMENT[subclass];
    return weapons
      .filter((w) => w.verdict === "god_roll" || w.verdict === "upgrade")
      .filter((w) => el === "" || w.element === el || w.element === "Kinetic")
      .sort((a, b) =>
        (VERDICT_RANK[a.verdict] ?? 9) - (VERDICT_RANK[b.verdict] ?? 9) || b.power - a.power)
      .slice(0, 8);
  }, [weapons, subclass]);

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
      <p style={{ color: "var(--muted)", maxWidth: 760 }}>
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

      <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 16, marginBottom: 28, maxWidth: 760 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <h2 style={{ margin: 0 }}>{cls} · {subclass}</h2>
          <button onClick={save} disabled={!dirty} style={{ padding: "4px 16px" }}>
            {dirty ? "Save" : saved ? "Saved ✓" : "Saved"}
          </button>
        </div>
        {FIELDS.map(([field, label]) => (
          <div key={field} style={{ marginBottom: 8 }}>
            <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--muted)", marginBottom: 2 }}>
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

      <h2 style={{ marginTop: 0 }}>
        Your best weapons{SUBCLASS_ELEMENT[subclass] ? ` for ${subclass}` : ""}
      </h2>
      {bestWeapons.length === 0 ? (
        <p style={{ color: "var(--muted)" }}>
          No god-roll / upgrade {SUBCLASS_ELEMENT[subclass]} (or Kinetic) weapons found in your
          inventory yet. Load the Weapons tab and rate some perks.
        </p>
      ) : (
        <div style={{
          display: "grid", gap: 8, marginBottom: 24,
          gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
        }}>
          {bestWeapons.map((w) => (
            <div key={w.instanceId} style={{
              display: "flex", gap: 8, alignItems: "center",
              border: "1px solid var(--border)", borderRadius: 6, padding: 8,
            }}>
              <Icon path={w.icon} size={36} alt={w.name} />
              <div style={{ minWidth: 0 }}>
                <strong style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {w.name}
                </strong>
                <span style={{ fontSize: 12, color: "var(--muted)" }}>
                  {w.weaponType} · <span style={{ color: elementColor(w.element) }}>{w.element}</span>
                  {" · "}{w.verdict.replace("_", " ")}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      <h2 style={{ marginTop: 0 }}>Armor optimizer</h2>
      <ArmorPage />
    </div>
  );
}
