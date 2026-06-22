import { useEffect, useMemo, useState } from "react";
import { bulkMove, fetchActivities, fetchCharacters, fetchLoadoutSuggestion } from "../api";
import { suggestedItems } from "../loadoutSuggestion";
import { ActivityRec, Character, LoadoutSuggestion } from "../types";
import { WeaponCard } from "./WeaponCard";

const SLOTS: ("Primary" | "Special" | "Heavy")[] = ["Primary", "Special", "Heavy"];

export function LoadoutBuilder() {
  const [activities, setActivities] = useState<ActivityRec[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [activity, setActivity] = useState("");
  const [data, setData] = useState<LoadoutSuggestion | null>(null);
  const [target, setTarget] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    fetchActivities().then((a) => {
      setActivities(a);
      if (a.length) setActivity(a[0].name);
    }).catch(() => setActivities([]));
    fetchCharacters().then((c) => {
      setCharacters(c);
      if (c.length) setTarget(c[0].id);
    }).catch(() => setCharacters([]));
  }, []);

  useEffect(() => {
    if (!activity) return;
    setError("");
    setStatus("");
    setData(null);
    fetchLoadoutSuggestion(activity).then(setData).catch((e) => setError(String(e)));
  }, [activity]);

  const items = useMemo(() => (data ? suggestedItems(data) : []), [data]);

  async function apply() {
    if (!data || !target || !items.length) return;
    setStatus("Applying…");
    try {
      const results = await bulkMove(items, target, true);
      const failed = results.filter((r) => !r.ok);
      setStatus(failed.length ? `Applied with ${failed.length} failure(s)` : "Applied ✓");
    } catch (e) {
      setStatus("");
      setError(String(e));
    }
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
        <select value={activity} onChange={(e) => setActivity(e.target.value)}
          style={{ background: "var(--panel)", color: "inherit", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 10px" }}>
          {activities.map((a) => <option key={a.name} value={a.name}>{a.name}</option>)}
        </select>
        <select value={target} onChange={(e) => setTarget(e.target.value)}
          style={{ background: "var(--panel)", color: "inherit", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 10px" }}>
          {characters.map((c) => <option key={c.id} value={c.id}>{c.className} ({c.light})</option>)}
        </select>
        <button onClick={apply} disabled={!items.length || !target}
          style={{ background: "var(--accent)", color: "#0a0e16", border: "none", borderRadius: 6, padding: "6px 14px", cursor: items.length ? "pointer" : "default", fontWeight: 700 }}>
          Equip weapons
        </button>
        {status && <span style={{ alignSelf: "center", color: "var(--muted)" }}>{status}</span>}
      </div>

      {error && <p style={{ color: "#c62828" }}>{error}</p>}

      {data && (
        <>
          <section style={{ marginBottom: 20 }}>
            <h2 style={{ borderBottom: "1px solid var(--border)", paddingBottom: 6 }}>
              Subclass: {data.subclass.class} {data.subclass.subclass}
            </h2>
            {data.subclass.build ? (
              <dl style={{ display: "grid", gridTemplateColumns: "max-content 1fr", gap: "2px 12px", margin: 0 }}>
                {Object.entries(data.subclass.build).map(([k, v]) => (
                  <div key={k} style={{ display: "contents" }}>
                    <dt style={{ color: "var(--muted)", textTransform: "capitalize" }}>{k}</dt>
                    <dd style={{ margin: 0 }}>{v}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p style={{ color: "var(--muted)" }}>No specific subclass build for this activity.</p>
            )}
          </section>

          <p style={{ color: "var(--muted)" }}>
            Element coverage: {data.elementCoverage.elements.join(", ") || "—"}
            {data.elementCoverage.activityElement &&
              ` · activity favors ${data.elementCoverage.activityElement}` +
              (data.elementCoverage.matchesActivity ? " ✓" : " (not covered)")}
          </p>

          {data.guidance && <p style={{ color: "var(--muted)", fontStyle: "italic" }}>{data.guidance}</p>}

          {SLOTS.map((slot) => (
            <section key={slot} style={{ marginBottom: 16 }}>
              <h3 style={{ margin: "8px 0" }}>{slot}</h3>
              {data.weapons[slot] ? (
                <WeaponCard w={data.weapons[slot]!} onClick={() => {}} />
              ) : (
                <p style={{ color: "var(--muted)" }}>No qualifying weapon owned.</p>
              )}
            </section>
          ))}
        </>
      )}
    </div>
  );
}
