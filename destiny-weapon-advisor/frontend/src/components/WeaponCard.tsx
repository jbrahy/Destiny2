import { Verdict, VERDICT_LABEL, WeaponDto } from "../types";
import { elementColor } from "../visual";
import { Icon } from "./Icon";
import { TagChip } from "./TagSelect";

/** A shapeable verdict is about potential, not the current roll. Without a
 *  marker a god-roll badge on a mediocre roll reads as a bug. */
function ShapeableChip() {
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, color: "#fff", background: "#6a1b9a",
      borderRadius: 4, padding: "1px 5px", marginLeft: 6, whiteSpace: "nowrap",
    }} title="Verdict reflects the best roll this crafted weapon could be shaped into">
      shapeable
    </span>
  );
}

const BADGE: Record<Verdict, { label: string; color: string }> = {
  god_roll: { label: VERDICT_LABEL.god_roll, color: "#2e7d32" },
  masterwork: { label: VERDICT_LABEL.masterwork, color: "#1565c0" },
  good: { label: VERDICT_LABEL.good, color: "#f9a825" },
  no_data: { label: VERDICT_LABEL.no_data, color: "#9e9e9e" },
  dismantle: { label: VERDICT_LABEL.dismantle, color: "#c62828" },
};

export function WeaponCard({
  w, tag, comparing, onToggleCompare, onClick,
}: {
  w: WeaponDto;
  tag?: string;
  comparing?: boolean;
  onToggleCompare?: () => void;
  onClick: () => void;
}) {
  const badge = BADGE[w.verdict];
  return (
    <div
      onClick={onClick}
      style={{
        display: "flex", gap: 10, alignItems: "flex-start", background: "var(--panel)",
        border: `1px solid ${comparing ? "var(--accent)" : "var(--border)"}`,
        borderRadius: 8, padding: 10, cursor: "pointer",
        borderLeft: `6px solid ${badge.color}`,
      }}
    >
      <Icon path={w.icon} size={44} alt={w.name} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
          <strong style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {w.name}
          </strong>
          <span style={{ display: "flex", gap: 6, alignItems: "center", whiteSpace: "nowrap" }}>
            {onToggleCompare && (
              <button
                onClick={(e) => { e.stopPropagation(); onToggleCompare(); }}
                title="Compare"
                style={{
                  padding: "0 6px", fontSize: 12, borderRadius: 4,
                  color: comparing ? "#0a0e16" : "var(--muted)",
                  background: comparing ? "var(--accent)" : "transparent",
                  border: "1px solid var(--border)",
                }}
              >⇄</button>
            )}
            <TagChip tag={tag} />
            <span style={{ color: badge.color, fontWeight: 600 }}>{badge.label}</span>
            {w.scoredFrom === "shapeable" && <ShapeableChip />}
          </span>
        </div>
        <div style={{ fontSize: 12, color: "var(--muted)", display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
          <span>{w.weaponType}</span>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: elementColor(w.element), display: "inline-block" }} />
          <span>{w.element}</span>
          {w.ammoType && <span>· {w.ammoType}</span>}
          <span>· {w.location}</span>
          {w.isMasterworked && <span>· ★</span>}
          {w.equipped && <span style={{ color: "#2e7d32", fontWeight: 600 }}>· equipped</span>}
        </div>
        <div style={{ fontSize: 12, color: "var(--text)", marginTop: 2 }}>
          {w.power > 0 && <span style={{ fontWeight: 600 }}>✦ {w.power}</span>}
          {w.frame && <span> · {w.frame}</span>}
        </div>
      </div>
    </div>
  );
}
