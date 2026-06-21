import { WeaponDto } from "../types";

function StatBar({ name, value }: { name: string; value: number }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
      <span style={{ width: 130, fontSize: 12, color: "#555" }}>{name}</span>
      <div style={{ flex: 1, background: "#eee", borderRadius: 3, height: 10 }}>
        <div style={{ width: `${pct}%`, background: "#1565c0", height: 10, borderRadius: 3 }} />
      </div>
      <span style={{ width: 32, textAlign: "right", fontSize: 12 }}>{value}</span>
    </div>
  );
}

export function WeaponDetail({ w, onClose }: { w: WeaponDto; onClose: () => void }) {
  const meta = [w.weaponType, w.element, w.ammoType, w.location].filter(Boolean).join(" · ");
  const statEntries = Object.entries(w.stats);
  return (
    <div style={{ border: "1px solid #ccc", borderRadius: 8, padding: 16, marginBottom: 16 }}>
      <button onClick={onClose} style={{ float: "right" }}>Close</button>
      <h2 style={{ margin: "0 0 4px" }}>{w.name}</h2>
      <p style={{ margin: "0 0 8px", color: "#666" }}>{meta}{w.isMasterworked ? " · ★ Masterworked" : ""}</p>
      <p style={{ margin: "0 0 8px" }}>
        {w.power > 0 && <strong>✦ {w.power} Power</strong>}
        {w.frame && <span> · {w.frame}</span>}
      </p>

      <p style={{ margin: "0 0 4px" }}><strong>Verdict:</strong> {w.verdict.replace("_", " ")}</p>
      {w.tags.length > 0 && <p style={{ margin: "0 0 4px" }}><strong>Best for:</strong> {w.tags.join(", ")}</p>}

      {w.ratedPerks.length > 0 ? (
        <>
          <h3 style={{ margin: "12px 0 4px" }}>Why (rated perks)</h3>
          {w.ratedPerks.map((p) => (
            <div key={p.name} style={{ marginBottom: 3 }}>
              <strong>{p.rating}</strong> · {p.name}
              {p.reason && <span style={{ color: "#666" }}> — {p.reason}</span>}
            </div>
          ))}
        </>
      ) : (
        <p style={{ margin: "8px 0 4px", color: "#666" }}>
          None of this weapon's perks are rated yet — add ratings on the Perks tab.
        </p>
      )}

      {w.perkNames.length > 0 && (
        <>
          <h3 style={{ margin: "12px 0 4px" }}>Roll</h3>
          <p style={{ margin: 0 }}>{w.perkNames.join(" · ")}</p>
        </>
      )}

      {statEntries.length > 0 && (
        <>
          <h3 style={{ margin: "12px 0 6px" }}>Stats</h3>
          {statEntries.map(([name, value]) => (
            <StatBar key={name} name={name} value={value} />
          ))}
        </>
      )}
    </div>
  );
}
