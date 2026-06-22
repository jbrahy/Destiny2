import { Verdict, WeaponDto } from "../types";
import { elementColor } from "../visual";
import { Icon } from "./Icon";

const BADGE: Record<Verdict, { label: string; color: string }> = {
  god_roll: { label: "God Roll", color: "#2e7d32" },
  upgrade: { label: "Upgrade", color: "#1565c0" },
  good: { label: "Good", color: "#f9a825" },
  no_data: { label: "No Data", color: "#9e9e9e" },
  dismantle: { label: "Dismantle", color: "#c62828" },
};

export function WeaponCard({ w, onClick }: { w: WeaponDto; onClick: () => void }) {
  const badge = BADGE[w.verdict];
  return (
    <div
      onClick={onClick}
      style={{
        display: "flex", gap: 10, alignItems: "flex-start",
        border: "1px solid #ddd", borderRadius: 8, padding: 10, cursor: "pointer",
        borderLeft: `6px solid ${badge.color}`,
      }}
    >
      <Icon path={w.icon} size={44} alt={w.name} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
          <strong style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {w.name}
          </strong>
          <span style={{ color: badge.color, fontWeight: 600, whiteSpace: "nowrap" }}>
            {badge.label}
          </span>
        </div>
        <div style={{ fontSize: 12, color: "#666", display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
          <span>{w.weaponType}</span>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: elementColor(w.element), display: "inline-block" }} />
          <span>{w.element}</span>
          {w.ammoType && <span>· {w.ammoType}</span>}
          <span>· {w.location}</span>
          {w.isMasterworked && <span>· ★</span>}
        </div>
        <div style={{ fontSize: 12, color: "#333", marginTop: 2 }}>
          {w.power > 0 && <span style={{ fontWeight: 600 }}>✦ {w.power}</span>}
          {w.frame && <span> · {w.frame}</span>}
        </div>
      </div>
    </div>
  );
}
