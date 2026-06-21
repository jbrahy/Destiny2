import { useEffect, useState } from "react";
import { fetchMemberships, selectMembership } from "../api";
import { Membership } from "../types";

const PLATFORM: Record<number, string> = { 1: "Xbox", 2: "PSN", 3: "Steam", 5: "Stadia", 6: "Epic" };

export function AccountSwitcher() {
  const [memberships, setMemberships] = useState<Membership[]>([]);
  const [active, setActive] = useState("");

  useEffect(() => {
    fetchMemberships()
      .then((d) => {
        setMemberships(d.memberships);
        if (d.active) setActive(d.active.id);
      })
      .catch(() => setMemberships([]));
  }, []);

  if (memberships.length <= 1) return null;

  async function onChange(id: string) {
    const m = memberships.find((x) => x.id === id);
    if (!m) return;
    await selectMembership(m.type, m.id);
    window.location.reload();
  }

  return (
    <select
      value={active}
      onChange={(e) => onChange(e.target.value)}
      title="Switch Destiny account"
      style={{ marginLeft: "auto", padding: "4px 8px", borderRadius: 6 }}
    >
      {memberships.map((m) => (
        <option key={m.id} value={m.id}>
          {(PLATFORM[m.type] || "Account") + ": " + m.displayName}
        </option>
      ))}
    </select>
  );
}
