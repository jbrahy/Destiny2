import { Verdict, WeaponDto } from "../types";

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
        border: "1px solid #ddd", borderRadius: 8, padding: 12, cursor: "pointer",
        borderLeft: `6px solid ${badge.color}`,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <strong>{w.name}</strong>
        <span style={{ color: badge.color, fontWeight: 600 }}>{badge.label}</span>
      </div>
      <div style={{ fontSize: 12, color: "#666" }}>
        {w.weaponType} · {w.element} · {w.location}
        {w.isMasterworked ? " · ★" : ""}
      </div>
    </div>
  );
}
