import { useEffect, useMemo, useState } from "react";
import { fetchActivities, saveActivity } from "../api";
import { ActivityRec } from "../types";

function ActivityCard({ activity }: { activity: ActivityRec }) {
  const [draft, setDraft] = useState<ActivityRec>(activity);
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);

  function set(field: keyof ActivityRec, value: string) {
    setDraft((d) => ({ ...d, [field]: value }));
    setDirty(true);
    setSaved(false);
  }

  async function save() {
    await saveActivity(draft.name, draft);
    setDirty(false);
    setSaved(true);
  }

  const field = (label: string, key: keyof ActivityRec, long = false) => (
    <div style={{ marginBottom: 6 }}>
      <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "var(--muted)" }}>{label}</label>
      {long ? (
        <textarea value={draft[key]} onChange={(e) => set(key, e.target.value)} rows={2}
          style={{ width: "100%", padding: 5, boxSizing: "border-box" }} />
      ) : (
        <input value={draft[key]} onChange={(e) => set(key, e.target.value)}
          style={{ width: "100%", padding: 5, boxSizing: "border-box" }} />
      )}
    </div>
  );

  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 14, marginBottom: 12, maxWidth: 760 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <h3 style={{ margin: 0 }}>{draft.name} <span style={{ color: "var(--muted)", fontWeight: 400, fontSize: 13 }}>· {draft.type}</span></h3>
        <button onClick={save} disabled={!dirty} style={{ padding: "4px 14px" }}>
          {dirty ? "Save" : saved ? "Saved ✓" : "Saved"}
        </button>
      </div>
      <div style={{ display: "flex", gap: 10 }}>
        <div style={{ flex: 1 }}>{field("Class", "recommendedClass")}</div>
        <div style={{ flex: 1 }}>{field("Subclass", "recommendedSubclass")}</div>
        <div style={{ flex: 1 }}>{field("Type", "type")}</div>
      </div>
      {field("Weapons", "weapons", true)}
      {field("Notes", "notes", true)}
    </div>
  );
}

export function ActivitiesPage() {
  const [activities, setActivities] = useState<ActivityRec[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");

  useEffect(() => {
    fetchActivities().then(setActivities).catch((e) => setError(e.message)).finally(() => setLoading(false));
  }, []);

  const types = useMemo(
    () => Array.from(new Set(activities.map((a) => a.type))).sort(),
    [activities],
  );
  const shown = useMemo(
    () => activities.filter((a) => typeFilter === "all" || a.type === typeFilter),
    [activities, typeFilter],
  );

  async function add() {
    const name = newName.trim();
    if (!name || activities.some((a) => a.name === name)) return;
    const fresh: ActivityRec = {
      name, type: "Custom", recommendedClass: "", recommendedSubclass: "", weapons: "", notes: "",
    };
    await saveActivity(name, fresh);
    setActivities((prev) => [fresh, ...prev]);
    setNewName("");
  }

  if (loading) return <div>Loading activities…</div>;
  if (error) return <div style={{ color: "#c62828" }}>Error: {error}</div>;

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Activities</h1>
      <p style={{ color: "var(--muted)", maxWidth: 760 }}>
        Recommended loadout per activity, seeded from general knowledge.{" "}
        <em>Verify against the current rotation</em> (champions and burns change) and edit freely.
        Add any activity that's missing — newer raids/seasons aren't pre-loaded.
      </p>
      <div style={{ display: "flex", gap: 8, marginBottom: 14, alignItems: "center", flexWrap: "wrap" }}>
        <input placeholder="Add an activity…" value={newName} onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()} style={{ padding: 6, width: 240 }} />
        <button onClick={add} style={{ padding: "6px 14px" }}>Add</button>
        <span style={{ marginLeft: 12, fontSize: 13, color: "var(--muted)" }}>Filter:</span>
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
          <option value="all">All types</option>
          {types.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>
      {shown.map((a) => <ActivityCard key={a.name} activity={a} />)}
    </div>
  );
}
