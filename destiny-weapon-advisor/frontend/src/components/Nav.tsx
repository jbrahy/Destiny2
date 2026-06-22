import { AccountSwitcher } from "./AccountSwitcher";
import { VaultCounts } from "./VaultCounts";

export type Section = "weapons" | "recommend" | "perks" | "armor" | "builds" | "activities" | "loadouts";

export const SECTIONS: { id: Section; label: string }[] = [
  { id: "weapons", label: "Weapons" },
  { id: "recommend", label: "Recommend" },
  { id: "perks", label: "Perks" },
  { id: "armor", label: "Armor" },
  { id: "builds", label: "Builds" },
  { id: "activities", label: "Activities" },
  { id: "loadouts", label: "Loadouts" },
];

export function Nav({ current, onChange }: { current: Section; onChange: (s: Section) => void }) {
  return (
    <header
      style={{
        position: "sticky", top: 0, zIndex: 10,
        display: "flex", alignItems: "center", gap: 18, padding: "12px 24px",
        background: "rgba(10, 14, 22, 0.82)", backdropFilter: "blur(10px)",
        borderBottom: "1px solid var(--border)",
      }}
    >
      <strong style={{
        fontFamily: "'Chakra Petch', sans-serif", fontSize: 17, letterSpacing: "0.08em",
        textTransform: "uppercase", whiteSpace: "nowrap",
      }}>
        <span style={{ color: "var(--accent)" }}>◆</span> Destiny&nbsp;2{" "}
        <span style={{ color: "var(--accent)" }}>Advisor</span>
      </strong>
      <nav style={{ display: "flex", gap: 2 }}>
        {SECTIONS.map((s) => {
          const active = s.id === current;
          return (
            <button
              key={s.id}
              onClick={() => onChange(s.id)}
              style={{
                background: "transparent", border: "none", borderRadius: 0,
                color: active ? "var(--accent)" : "var(--muted)",
                fontWeight: active ? 700 : 500, padding: "6px 11px",
                borderBottom: `2px solid ${active ? "var(--accent)" : "transparent"}`,
                textTransform: "uppercase", letterSpacing: "0.05em", cursor: "pointer",
              }}
            >
              {s.label}
            </button>
          );
        })}
      </nav>
      <VaultCounts />
      <AccountSwitcher />
      <a
        href="/api/login"
        title="Re-authorize with Bungie (needed to enable moving/equipping items)"
        style={{ marginLeft: 12, color: "var(--muted)", fontSize: 12 }}
      >
        Re-login
      </a>
    </header>
  );
}
