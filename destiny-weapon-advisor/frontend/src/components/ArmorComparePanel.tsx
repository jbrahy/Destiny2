import { ArmorPiece } from "../types";
import { Icon } from "./Icon";

const total = (a: ArmorPiece) => Object.values(a.stats).reduce((x, y) => x + y, 0);

export function ArmorComparePanel({
  items, onRemove, onClear,
}: {
  items: ArmorPiece[];
  onRemove: (id: string) => void;
  onClear: () => void;
}) {
  if (items.length < 2) return null;
  const statNames = Array.from(new Set(items.flatMap((a) => Object.keys(a.stats))));
  const rows: { label: string; get: (a: ArmorPiece) => string | number; numeric?: boolean }[] = [
    { label: "Power", get: (a) => a.power, numeric: true },
    { label: "Slot", get: (a) => a.slot },
    { label: "Total", get: (a) => total(a), numeric: true },
    ...statNames.map((s) => ({ label: s, get: (a: ArmorPiece) => a.stats[s] ?? 0, numeric: true })),
  ];

  return (
    <div style={{
      border: "1px solid var(--accent)", borderRadius: 8, padding: 14, marginBottom: 14,
      background: "var(--panel)",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <strong>Comparing {items.length} armor pieces</strong>
        <button onClick={onClear}>Clear</button>
      </div>
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr>
            <th />
            {items.map((a) => (
              <th key={a.instanceId} style={{ padding: 6, textAlign: "center", verticalAlign: "top" }}>
                <Icon path={a.icon} size={32} alt={a.name} border={a.isExotic ? "#caa000" : undefined} />
                <div style={{ fontSize: 12, maxWidth: 120 }}>{a.name}</div>
                <button onClick={() => onRemove(a.instanceId)} style={{ fontSize: 11, marginTop: 2 }}>remove</button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const vals = items.map((a) => row.get(a));
            const max = row.numeric ? Math.max(...vals.map((v) => Number(v) || 0)) : 0;
            return (
              <tr key={row.label} style={{ borderTop: "1px solid var(--border)" }}>
                <td style={{ padding: 6, color: "var(--muted)", fontSize: 12 }}>{row.label}</td>
                {items.map((a, i) => {
                  const v = vals[i];
                  const best = !!row.numeric && max > 0 && Number(v) === max;
                  return (
                    <td key={a.instanceId} style={{
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
