import { useEffect, useMemo, useState } from "react";
import { fetchPerks, savePerkRating } from "../api";
import { CatalogPerk, WeaponTypePerks } from "../types";

const TIERS = ["", "S", "A", "B", "C", "D"];
const TIER_COLOR: Record<string, string> = {
  S: "#2e7d32", A: "#1565c0", B: "#f9a825", C: "#9e9e9e", D: "#c62828", "": "#bbb",
};

export function PerksPage() {
  const [groups, setGroups] = useState<WeaponTypePerks[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState<Record<string, boolean>>({});

  useEffect(() => {
    fetchPerks().then(setGroups).catch((e) => setError(e.message)).finally(() => setLoading(false));
  }, []);

  function patch(weaponType: string, name: string, changes: Partial<CatalogPerk>) {
    setGroups((prev) =>
      prev.map((g) =>
        g.weaponType !== weaponType
          ? g
          : {
              ...g,
              perks: g.perks.map((p) =>
                p.name === name ? { ...p, ...changes, dirty: true } : p,
              ),
            },
      ),
    );
  }

  async function save(weaponType: string, perk: CatalogPerk) {
    try {
      await savePerkRating({
        name: perk.name, weaponType, rating: perk.rating,
        reason: perk.reason, tags: perk.tags, notes: perk.notes,
      });
      setGroups((prev) =>
        prev.map((g) =>
          g.weaponType !== weaponType
            ? g
            : {
                ...g,
                perks: g.perks.map((p) =>
                  p.name === perk.name ? { ...p, dirty: false, isOverride: true } : p,
                ),
              },
        ),
      );
    } catch (e) {
      setError(String(e));
    }
  }

  const filtered = useMemo(
    () =>
      groups
        .map((g) => ({
          ...g,
          perks: g.perks.filter((p) => p.name.toLowerCase().includes(search.toLowerCase())),
        }))
        .filter((g) => g.perks.length > 0),
    [groups, search],
  );

  if (loading) return <div>Loading perks…</div>;
  if (error) return <div style={{ color: "#c62828" }}>Error: {error}</div>;
  if (groups.length === 0)
    return (
      <div style={{ color: "#666" }}>
        Open the <strong>Weapons</strong> tab first — perks are gathered from your inventory.
      </div>
    );

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Perk Ratings</h1>
      <p style={{ color: "#666", maxWidth: 720 }}>
        Rate each perk <strong>per weapon type</strong> and add your own notes. Seeded from general
        PvE/PvP knowledge — edit freely; weapon verdicts update on your next{" "}
        <strong>Refresh</strong>. <em>Verify against the current season.</em>
      </p>
      <input
        placeholder="Search perks…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        style={{ marginBottom: 12, padding: 6, width: 260 }}
      />
      {filtered.map((g) => {
        const isOpen = open[g.weaponType] ?? false;
        return (
          <div key={g.weaponType} style={{ border: "1px solid #ddd", borderRadius: 8, marginBottom: 10 }}>
            <div
              onClick={() => setOpen((o) => ({ ...o, [g.weaponType]: !isOpen }))}
              style={{
                padding: "10px 14px", cursor: "pointer", fontWeight: 600,
                background: "#f5f5f5", borderRadius: 8,
              }}
            >
              {isOpen ? "▾" : "▸"} {g.weaponType}{" "}
              <span style={{ color: "#999", fontWeight: 400 }}>({g.perks.length})</span>
            </div>
            {isOpen && (
              <div style={{ padding: "8px 14px" }}>
                {g.perks.map((p) => (
                  <div
                    key={p.name}
                    style={{ padding: "10px 0", borderBottom: "1px solid #f1f1f1" }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <select
                        value={p.rating}
                        onChange={(e) => patch(g.weaponType, p.name, { rating: e.target.value })}
                        style={{ width: 52, fontWeight: 700, color: TIER_COLOR[p.rating] || "#333" }}
                      >
                        {TIERS.map((t) => (
                          <option key={t} value={t}>{t || "—"}</option>
                        ))}
                      </select>
                      <strong style={{ minWidth: 200 }}>{p.name}</strong>
                      {p.isOverride && (
                        <span title="weapon-type override" style={{ fontSize: 11, color: "#1565c0" }}>
                          ★ override
                        </span>
                      )}
                      <button
                        onClick={() => save(g.weaponType, p)}
                        disabled={!p.dirty}
                        style={{ marginLeft: "auto", padding: "4px 14px" }}
                      >
                        {p.dirty ? "Save" : "Saved"}
                      </button>
                    </div>
                    {p.description && (
                      <p style={{ margin: "4px 0 2px", fontSize: 13, color: "#444" }}>{p.description}</p>
                    )}
                    {p.reason && (
                      <p style={{ margin: "2px 0", fontSize: 12, color: "#888" }}>
                        <em>Why this tier:</em> {p.reason}
                      </p>
                    )}
                    <textarea
                      value={p.notes}
                      placeholder="Your notes…"
                      onChange={(e) => patch(g.weaponType, p.name, { notes: e.target.value })}
                      rows={2}
                      style={{ width: "100%", marginTop: 4, padding: 6, boxSizing: "border-box" }}
                    />
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
