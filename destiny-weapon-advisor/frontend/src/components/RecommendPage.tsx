import { useEffect, useState } from "react";
import { fetchActivities, fetchRecommendations } from "../api";
import { buildContextOptions } from "../recommend";
import { ActivityRec, Recommendations } from "../types";
import { WeaponCard } from "./WeaponCard";

const SLOTS: ("Primary" | "Special" | "Heavy")[] = ["Primary", "Special", "Heavy"];

export function RecommendPage() {
  const [activities, setActivities] = useState<ActivityRec[]>([]);
  const [context, setContext] = useState("general-pve");
  const [data, setData] = useState<Recommendations | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchActivities().then(setActivities).catch(() => setActivities([]));
  }, []);

  useEffect(() => {
    setError("");
    fetchRecommendations(context).then(setData).catch((e) => setError(String(e)));
  }, [context]);

  const options = buildContextOptions(activities);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>Recommended Weapons</h1>
        <select
          value={context}
          onChange={(e) => setContext(e.target.value)}
          style={{
            background: "var(--panel)", color: "var(--text, inherit)",
            border: "1px solid var(--border)", borderRadius: 6, padding: "6px 10px",
          }}
        >
          {options.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      {context === "general-pvp" && (
        <p style={{ color: "var(--muted)", marginTop: 0 }}>
          Note: ratings are PvE-oriented. PvP-specific ratings are coming later.
        </p>
      )}

      {error && <p style={{ color: "#c62828" }}>{error}</p>}

      {data && SLOTS.map((slot) => (
        <section key={slot} style={{ marginBottom: 24 }}>
          <h2 style={{ borderBottom: "1px solid var(--border)", paddingBottom: 6 }}>{slot}</h2>
          {data.slots[slot].length === 0 ? (
            <p style={{ color: "var(--muted)" }}>No qualifying weapons. Refresh your vault on the Weapons tab.</p>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 10 }}>
              {data.slots[slot].map((w) => (
                <div key={w.instanceId}>
                  <WeaponCard w={w} onClick={() => {}} />
                  <div style={{ fontSize: 12, color: "var(--muted)", padding: "2px 10px 0" }}>
                    {w.recommendReason}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      ))}
    </div>
  );
}
