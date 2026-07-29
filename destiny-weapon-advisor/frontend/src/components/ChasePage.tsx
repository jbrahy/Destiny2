import { useEffect, useState } from "react";
import { ChaseRow, fetchChase } from "../api";
import { Verdict, VERDICT_LABEL } from "../types";
import { ICON_BASE } from "../visual";

const VERDICT_COLOR: Record<string, string> = {
  god_roll: "#2e7d32",
  masterwork: "#1565c0",
  good: "#f9a825",
  no_data: "#9e9e9e",
  dismantle: "#c62828",
};

function label(v: string): string {
  return VERDICT_LABEL[v as Verdict] ?? v;
}

export function ChasePage() {
  const [rows, setRows] = useState<ChaseRow[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchChase()
      .then(setRows)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Worth Chasing</h1>
      <p style={{ color: "var(--muted)", maxWidth: 720 }}>
        Weapons you already own that can roll better than your best copy. The
        possible perks come from the weapon's actual roll pool, and perks that no
        longer drop are excluded — so nothing here is a dead grind.
      </p>

      {error && <p style={{ color: "#c62828" }}>{error}</p>}
      {loading && <p style={{ color: "var(--muted)" }}>Loading…</p>}

      {!loading && !error && rows.length === 0 && (
        <p style={{ color: "var(--muted)" }}>
          Nothing to chase — every weapon in your vault is already at its ceiling,
          or its pool has no top-tier perks rated yet. Rate more perks on the Perks
          tab to sharpen this.
        </p>
      )}

      {rows.length > 0 && (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left", color: "var(--muted)" }}>
              <th /><th>Weapon</th><th>You have</th><th>Could roll</th><th>Chase perks</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.itemHash} style={{ borderTop: "1px solid var(--border)" }}>
                <td style={{ width: 40 }}>
                  {r.icon && (
                    <img src={`${ICON_BASE}${r.icon}`} alt="" width={32} height={32} />
                  )}
                </td>
                <td>
                  <div>{r.name}</div>
                  <div style={{ fontSize: 11, color: "var(--muted)" }}>
                    {r.weaponType} · {r.haveCount} owned
                  </div>
                </td>
                <td>
                  <span style={{ color: VERDICT_COLOR[r.ownedBest] ?? "var(--muted)" }}>
                    {label(r.ownedBest)}
                  </span>
                </td>
                <td>
                  <span style={{ color: VERDICT_COLOR[r.ceiling] ?? "var(--muted)", fontWeight: 700 }}>
                    {label(r.ceiling)}
                  </span>
                </td>
                <td>{r.chasePerks.join(" + ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
