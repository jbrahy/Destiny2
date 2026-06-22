import { useEffect, useState } from "react";
import {
  applyLoadout, deleteLoadout, fetchArmor, fetchCharacters, fetchLoadouts,
  fetchPostmaster, fetchWeapons, pullPostmaster, saveLoadout,
} from "../api";
import { ArmorPiece, Character, Loadout, PostmasterItem, WeaponDto } from "../types";
import { Icon } from "./Icon";

export function LoadoutsPage() {
  const [characters, setCharacters] = useState<Character[]>([]);
  const [loadouts, setLoadouts] = useState<Loadout[]>([]);
  const [postmaster, setPostmaster] = useState<PostmasterItem[]>([]);
  const [weapons, setWeapons] = useState<WeaponDto[]>([]);
  const [armor, setArmor] = useState<ArmorPiece[]>([]);
  const [charId, setCharId] = useState("");
  const [name, setName] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function reload() {
    fetchLoadouts().then(setLoadouts).catch(() => {});
    fetchPostmaster().then(setPostmaster).catch(() => {});
    fetchWeapons().then((r) => setWeapons(r.weapons)).catch(() => {});
    fetchArmor().then((d) => setArmor(d.armor)).catch(() => {});
  }

  useEffect(() => {
    fetchCharacters().then((cs) => { setCharacters(cs); if (cs[0]) setCharId(cs[0].id); }).catch(() => {});
    reload();
  }, []);

  const className = characters.find((c) => c.id === charId)?.className || "";

  function equippedItems() {
    return [
      ...weapons.filter((w) => w.equipped && w.location === className)
        .map((w) => ({ instanceId: w.instanceId, itemHash: w.itemHash })),
      ...armor.filter((a) => a.equipped && a.location === className)
        .map((a) => ({ instanceId: a.instanceId, itemHash: a.itemHash })),
    ];
  }

  async function save() {
    const items = equippedItems();
    if (!name.trim() || items.length === 0) {
      setMsg("Pick a character with equipped gear and enter a name.");
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      await saveLoadout(name.trim(), charId, items);
      setMsg(`Saved "${name.trim()}" (${items.length} items).`);
      setName("");
      fetchLoadouts().then(setLoadouts);
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function apply(lo: Loadout) {
    if (!window.confirm(`Apply "${lo.name}"? This moves & equips ${lo.items.length} items.`)) return;
    setBusy(true);
    setMsg(null);
    try {
      const res = await applyLoadout(lo.name);
      const fail = res.filter((r) => !r.ok).length;
      setMsg(fail ? `Applied with ${fail} issue(s) — if it's a permission error, click Re-login.`
        : `✓ Applied "${lo.name}".`);
      reload();
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove(lo: Loadout) {
    if (!window.confirm(`Delete loadout "${lo.name}"?`)) return;
    await deleteLoadout(lo.name);
    fetchLoadouts().then(setLoadouts);
  }

  async function pull(it: PostmasterItem) {
    setBusy(true);
    setMsg(null);
    try {
      await pullPostmaster(it);
      reload();
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Loadouts</h1>
      {msg && <p style={{ color: msg.startsWith("✓") || msg.startsWith("Saved") ? "#2e7d32" : "#c62828" }}>{msg}</p>}

      <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 14, marginBottom: 20, maxWidth: 640 }}>
        <strong>Save a loadout</strong> from a character's currently-equipped gear:
        <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
          <select value={charId} onChange={(e) => setCharId(e.target.value)}>
            {characters.map((c) => <option key={c.id} value={c.id}>{c.className} ✦{c.light}</option>)}
          </select>
          <input placeholder="Loadout name…" value={name} onChange={(e) => setName(e.target.value)} />
          <button onClick={save} disabled={busy}>Save current {className} gear</button>
        </div>
        <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>
          Captures {equippedItems().length} equipped item(s) for {className || "—"}.
        </div>
      </div>

      <h2>Saved loadouts</h2>
      {loadouts.length === 0 && <p style={{ color: "var(--muted)" }}>None yet.</p>}
      {loadouts.map((lo) => (
        <div key={lo.name} style={{
          display: "flex", alignItems: "center", gap: 12, border: "1px solid var(--border)",
          borderRadius: 8, padding: "8px 12px", marginBottom: 8, maxWidth: 640,
        }}>
          <strong style={{ flex: 1 }}>{lo.name}</strong>
          <span style={{ color: "var(--muted)", fontSize: 13 }}>{lo.items.length} items</span>
          <button onClick={() => apply(lo)} disabled={busy}>Apply</button>
          <button onClick={() => remove(lo)} disabled={busy} style={{ color: "#c62828" }}>Delete</button>
        </div>
      ))}

      <h2 style={{ marginTop: 24 }}>Postmaster</h2>
      {postmaster.length === 0 ? (
        <p style={{ color: "var(--muted)" }}>Postmaster is empty.</p>
      ) : (
        <div style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))" }}>
          {postmaster.map((it) => (
            <div key={it.instanceId || `${it.characterId}-${it.itemHash}`} style={{
              display: "flex", gap: 8, alignItems: "center", border: "1px solid var(--border)", borderRadius: 6, padding: 8,
            }}>
              <Icon path={it.icon} size={36} alt={it.name} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <strong style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {it.name}{it.quantity > 1 ? ` ×${it.quantity}` : ""}
                </strong>
                <span style={{ fontSize: 12, color: "var(--muted)" }}>{it.className}</span>
              </div>
              <button onClick={() => pull(it)} disabled={busy}>Pull</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
