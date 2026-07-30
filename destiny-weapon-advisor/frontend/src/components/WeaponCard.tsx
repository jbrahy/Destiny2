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

/** One metadata item carrying its own leading separator, so a wrap can never
 *  strand a bare "·" at the end of one line or the start of the next. */
function Meta(
  { first, color, weight, title, children }: {
    first?: boolean; color?: string; weight?: number; title?: string;
    children: React.ReactNode;
  },
) {
  return (
    <span title={title} style={{ display: "inline-flex", alignItems: "center", gap: 5, color, fontWeight: weight }}>
      {!first && <span style={{ color: "var(--border)" }} aria-hidden>·</span>}
      {children}
    </span>
  );
}

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
        {/* The name owns this row. The verdict label sits below because
            "Masterwork → God Roll" is 5x the length of "Good" — sharing the row
            let it squeeze the name to zero width on exactly those cards. */}
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "baseline" }}>
          <strong style={{ fontSize: 15, lineHeight: 1.25, minWidth: 0, wordBreak: "break-word" }}>
            {w.name}
          </strong>
          <span style={{ display: "flex", gap: 6, alignItems: "center", flexShrink: 0 }}>
            <TagChip tag={tag} />
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
          </span>
        </div>

        {/* Separators are their own elements, not "· " glued to the next label,
            so wrapping can never strand a lone "· Vault" on its own line. */}
        <div style={{
          fontSize: 12, display: "flex", alignItems: "center",
          gap: 5, flexWrap: "wrap", marginTop: 3,
        }}>
          {/* What it is, and how good — the verdict leads because that is what
              you scan for across 751 cards. */}
          <Meta first color={badge.color} weight={700}>{badge.label}</Meta>
          {w.scoredFrom === "shapeable" && <ShapeableChip />}
          <Meta color="var(--muted)">
            <span style={{
              width: 8, height: 8, borderRadius: "50%",
              background: elementColor(w.element), flexShrink: 0,
            }} />
            {w.element} {w.weaponType}
          </Meta>
          {w.ammoType && <Meta color="var(--muted)">{w.ammoType}</Meta>}
        </div>

        {/* Where it is and what state it's in — a different question, so a
            different row. Splitting them keeps both short enough not to wrap. */}
        <div style={{
          fontSize: 12, color: "var(--text)", marginTop: 3,
          display: "flex", alignItems: "center", gap: 5, flexWrap: "wrap",
        }}>
          {w.power > 0 && <Meta first weight={600}>✦ {w.power}</Meta>}
          {w.frame && <Meta first={w.power <= 0}>{w.frame}</Meta>}
          <Meta color="var(--muted)">{w.location}</Meta>
          {w.isMasterworked && <Meta title="Masterworked">★</Meta>}
          {w.equipped && <Meta color="#2e7d32" weight={600}>equipped</Meta>}
        </div>

        {/* The reason the weapon earned its verdict. Omitted entirely when there
            is nothing to say, rather than leaving an empty row. */}
        {w.matchedPerks.length > 0 && (
          <div style={{
            fontSize: 12, marginTop: 3, color: "var(--accent)",
            display: "flex", alignItems: "center", gap: 5, flexWrap: "wrap",
          }}>
            {w.matchedPerks.map((p, i) => (
              <Meta key={p} first={i === 0}>{p}</Meta>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
