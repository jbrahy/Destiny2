import { AccountSwitcher } from "./AccountSwitcher";

export type Section = "weapons" | "perks" | "armor" | "builds";

export const SECTIONS: { id: Section; label: string }[] = [
  { id: "weapons", label: "Weapons" },
  { id: "perks", label: "Perks" },
  { id: "armor", label: "Armor" },
  { id: "builds", label: "Builds" },
];

export function Nav({ current, onChange }: { current: Section; onChange: (s: Section) => void }) {
  return (
    <header
      style={{
        position: "sticky", top: 0, zIndex: 10, background: "#1b2838", color: "#fff",
        display: "flex", alignItems: "center", gap: 24, padding: "12px 24px",
      }}
    >
      <strong style={{ fontSize: 18 }}>Destiny 2 Advisor</strong>
      <nav style={{ display: "flex", gap: 8 }}>
        {SECTIONS.map((s) => {
          const active = s.id === current;
          return (
            <button
              key={s.id}
              onClick={() => onChange(s.id)}
              style={{
                background: active ? "#fff" : "transparent",
                color: active ? "#1b2838" : "#cbd5e1",
                border: "1px solid #3a4a5e", borderRadius: 6,
                padding: "6px 14px", cursor: "pointer", fontWeight: active ? 700 : 500,
              }}
            >
              {s.label}
            </button>
          );
        })}
      </nav>
      <AccountSwitcher />
      <a
        href="/api/login"
        title="Re-authorize with Bungie (needed to enable moving/equipping items)"
        style={{ marginLeft: 12, color: "#cbd5e1", fontSize: 13 }}
      >
        Re-login
      </a>
    </header>
  );
}
