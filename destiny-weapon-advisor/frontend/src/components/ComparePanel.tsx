import { VERDICT_LABEL, WeaponDto } from "../types";
import { Icon } from "./Icon";

export function ComparePanel({
  items, onRemove, onClear,
}: {
  items: WeaponDto[];
  onRemove: (id: string) => void;
  onClear: () => void;
}) {
  if (items.length < 2) return null;
  const statNames = Array.from(new Set(items.flatMap((w) => Object.keys(w.stats))));
  const rows: { label: string; get: (w: WeaponDto) => string | number; numeric?: boolean }[] = [
    { label: "Power", get: (w) => w.power, numeric: true },
    { label: "Verdict", get: (w) => VERDICT_LABEL[w.verdict] },
    { label: "Element", get: (w) => w.element },
    { label: "Ammo", get: (w) => w.ammoType },
    { label: "Frame", get: (w) => w.frame },
    ...statNames.map((s) => ({ label: s, get: (w: WeaponDto) => w.stats[s] ?? 0, numeric: true })),
  ];

  return (
    <div style={{
      border: "1px solid var(--accent)", borderRadius: 8, padding: 14, marginBottom: 14,
      background: "var(--panel)",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <strong>Comparing {items.length} weapons</strong>
        <button onClick={onClear}>Clear</button>
      </div>
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr>
            <th />
            {items.map((w) => (
              <th key={w.instanceId} style={{ padding: 6, textAlign: "center", verticalAlign: "top" }}>
                <Icon path={w.icon} size={32} alt={w.name} />
                <div style={{ fontSize: 12, maxWidth: 120 }}>{w.name}</div>
                <button onClick={() => onRemove(w.instanceId)} style={{ fontSize: 11, marginTop: 2 }}>remove</button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const vals = items.map((w) => row.get(w));
            const max = row.numeric ? Math.max(...vals.map((v) => Number(v) || 0)) : 0;
            return (
              <tr key={row.label} style={{ borderTop: "1px solid var(--border)" }}>
                <td style={{ padding: 6, color: "var(--muted)", fontSize: 12 }}>{row.label}</td>
                {items.map((w, i) => {
                  const v = vals[i];
                  const best = !!row.numeric && max > 0 && Number(v) === max;
                  return (
                    <td key={w.instanceId} style={{
                      padding: 6, textAlign: "center",
                      color: best ? "var(--accent)" : undefined, fontWeight: best ? 700 : 400,
                    }}>{v || "—"}</td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
