import { useEffect, useMemo, useState } from "react";
import {
  applyArmorSet, deleteArmorSet, fetchArmor, fetchArmorSets, fetchCharacters, saveArmorSet,
} from "../api";
import { ArmorPiece, ArmorSet, Character } from "../types";
import { armorSetItems, armorSetTier } from "../armorSet";

const SLOTS = ["Helmet", "Gauntlets", "Chest Armor", "Leg Armor", "Class Item"];
const CLASSES = ["Titan", "Hunter", "Warlock"];

function objective(piece: ArmorPiece, stats: string[]): number {
  if (stats.length === 0) return Object.values(piece.stats).reduce((a, b) => a + b, 0);
  return stats.reduce((sum, s) => sum + (piece.stats[s] || 0), 0);
}

// Best piece per slot maximizing the objective, with at most one exotic where
// possible (a slot with no legendary is forced to its best exotic).
function optimize(pool: ArmorPiece[], stats: string[]) {
  const bySlot: Record<string, ArmorPiece[]> = {};
  for (const p of pool) (bySlot[p.slot] ||= []).push(p);

  const chosen: Record<string, ArmorPiece | null> = {};
  const exoticGain: { slot: string; piece: ArmorPiece; gain: number }[] = [];

  for (const slot of SLOTS) {
    const pieces = bySlot[slot] || [];
    const nonExotic = pieces.filter((p) => !p.isExotic);
    const best = (arr: ArmorPiece[]) =>
      arr.length ? arr.reduce((a, b) => (objective(b, stats) > objective(a, stats) ? b : a)) : null;
    const bestNon = best(nonExotic);
    const bestExo = best(pieces.filter((p) => p.isExotic));
    chosen[slot] = bestNon ?? bestExo; // fall back to exotic if no legendary in slot
    if (bestExo) {
      const baseline = bestNon ? objective(bestNon, stats) : 0;
      exoticGain.push({ slot, piece: bestExo, gain: objective(bestExo, stats) - baseline });
    }
  }

  // Apply the single most beneficial exotic swap (≤ 1 exotic), unless a slot is
  // already forced to an exotic (no legendary available there).
  const forcedExotic = SLOTS.some((s) => chosen[s]?.isExotic);
  if (!forcedExotic && exoticGain.length) {
    const best = exoticGain.reduce((a, b) => (b.gain > a.gain ? b : a));
    if (best.gain > 0) chosen[best.slot] = best.piece;
  }
  return chosen;
}

export function ArmorPage() {
  const [armor, setArmor] = useState<ArmorPiece[]>([]);
  const [statNames, setStatNames] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cls, setCls] = useState("Hunter");
  const [stats, setStats] = useState<string[]>([]);
  const [mins, setMins] = useState<Record<string, number>>({});
  const [characters, setCharacters] = useState<Character[]>([]);
  const [armorSets, setArmorSets] = useState<ArmorSet[]>([]);
  const [setName, setSetName] = useState("");
  const [targetChar, setTargetChar] = useState("");
  const [saveMsg, setSaveMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchCharacters().then(setCharacters).catch(() => setCharacters([]));
    fetchArmorSets().then(setArmorSets).catch(() => setArmorSets([]));
  }, []);

  const classChars = useMemo(
    () => characters.filter((c) => c.className === cls),
    [characters, cls],
  );

  useEffect(() => {
    setTargetChar(classChars[0]?.id ?? "");
  }, [classChars]);

  async function saveSet() {
    if (!setName.trim() || !targetChar || setItems.length === 0) {
      setSaveMsg("Enter a name and pick a character of this class.");
      return;
    }
    setBusy(true);
    setSaveMsg("");
    try {
      await saveArmorSet({
        name: setName.trim(), className: cls, characterId: targetChar,
        tier: armorSetTier(chosen), items: setItems,
      });
      setSaveMsg(`Saved "${setName.trim()}".`);
      setSetName("");
      fetchArmorSets().then(setArmorSets);
    } catch (e) {
      setSaveMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function applySet(s: ArmorSet) {
    if (!window.confirm(`Apply "${s.name}"? This moves & equips ${s.items.length} pieces.`)) return;
    setBusy(true);
    setSaveMsg("");
    try {
      const results = await applyArmorSet(s.name);
      const fail = results.filter((r) => !r.ok).length;
      setSaveMsg(fail ? `Applied with ${fail} issue(s) — if it's a permission error, click Re-login.`
        : `✓ Applied "${s.name}".`);
    } catch (e) {
      setSaveMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function removeSet(s: ArmorSet) {
    if (!window.confirm(`Delete armor set "${s.name}"?`)) return;
    try {
      await deleteArmorSet(s.name);
      fetchArmorSets().then(setArmorSets);
    } catch (e) {
      setSaveMsg(String(e));
    }
  }

  useEffect(() => {
    fetchArmor()
      .then((d) => { setArmor(d.armor); setStatNames(d.statNames); })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const availableClasses = useMemo(
    () => CLASSES.filter((c) => armor.some((a) => a.className === c)),
    [armor],
  );

  const pool = useMemo(
    () => armor.filter((a) => a.className === cls || a.className === "Any"),
    [armor, cls],
  );

  const minStats = useMemo(() => Object.keys(mins).filter((k) => mins[k] > 0), [mins]);
  const objectiveStats = useMemo(
    () => Array.from(new Set([...stats, ...minStats])),
    [stats, minStats],
  );
  const chosen = useMemo(() => optimize(pool, objectiveStats), [pool, objectiveStats]);
  const setItems = useMemo(() => armorSetItems(chosen), [chosen]);

  const totals = useMemo(() => {
    const t: Record<string, number> = {};
    for (const slot of SLOTS) {
      const p = chosen[slot];
      if (!p) continue;
      for (const [s, v] of Object.entries(p.stats)) t[s] = (t[s] || 0) + v;
    }
    return t;
  }, [chosen]);

  function toggleStat(s: string) {
    setStats((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]));
  }

  if (loading) return <div>Loading armor…</div>;
  if (error) return <div style={{ color: "#c62828" }}>Error: {error}</div>;
  if (armor.length === 0)
    return (
      <div style={{ color: "var(--muted)" }}>
        Open the <strong>Weapons</strong> tab first — armor is read from the same inventory pull.
      </div>
    );

  const shownStats = (stats.length || minStats.length)
    ? Array.from(new Set([...stats, ...minStats]))
    : statNames;

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Armor Optimizer</h1>
      <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
        {(availableClasses.length ? availableClasses : CLASSES).map((c) => (
          <button
            key={c}
            onClick={() => setCls(c)}
            style={{
              padding: "6px 14px", fontWeight: c === cls ? 700 : 400,
              background: c === cls ? "var(--accent)" : "var(--panel2)", color: c === cls ? "#0a0e16" : "var(--text)",
              border: "none", borderRadius: 6, cursor: "pointer",
            }}
          >
            {c}
          </button>
        ))}
      </div>

      <div style={{ marginBottom: 12 }}>
        <span style={{ fontSize: 13, color: "var(--muted)", marginRight: 8 }}>Prioritize stats:</span>
        {statNames.map((s) => (
          <label key={s} style={{ marginRight: 12, fontSize: 13 }}>
            <input type="checkbox" checked={stats.includes(s)} onChange={() => toggleStat(s)} /> {s}
          </label>
        ))}
        {stats.length === 0 && (
          <span style={{ color: "var(--muted)", fontSize: 12 }}>(none selected → maximizing total stats)</span>
        )}
      </div>

      <div style={{ marginBottom: 12 }}>
        <span style={{ fontSize: 13, color: "var(--muted)", marginRight: 8 }}>Minimum totals (optional):</span>
        {statNames.map((s) => (
          <label key={s} style={{ marginRight: 10, fontSize: 13 }}>
            {s.slice(0, 4)}{" "}
            <input
              type="number" min={0} value={mins[s] || ""}
              style={{ width: 48 }}
              onChange={(e) => setMins((m) => ({ ...m, [s]: Number(e.target.value) || 0 }))}
            />
          </label>
        ))}
      </div>

      <table style={{ borderCollapse: "collapse", width: "100%", maxWidth: 900 }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "2px solid var(--border)" }}>
            <th style={{ padding: 6 }}>Slot</th>
            <th style={{ padding: 6 }}>Piece</th>
            {shownStats.map((s) => (
              <th key={s} style={{ padding: 6, textAlign: "right" }}>{s.slice(0, 4)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {SLOTS.map((slot) => {
            const p = chosen[slot];
            return (
              <tr key={slot} style={{ borderBottom: "1px solid var(--border)" }}>
                <td style={{ padding: 6, color: "var(--muted)" }}>{slot}</td>
                <td style={{ padding: 6 }}>
                  {p ? (
                    <>
                      {p.name}{" "}
                      {p.isExotic && <span style={{ color: "#caa000", fontWeight: 700 }}>◆</span>}
                      {p.isMasterworked && <span title="masterworked"> ★</span>}
                      <span style={{ color: "var(--muted)", fontSize: 12 }}> · {p.location}</span>
                    </>
                  ) : (
                    <span style={{ color: "#bbb" }}>— none —</span>
                  )}
                </td>
                {shownStats.map((s) => (
                  <td key={s} style={{ padding: 6, textAlign: "right" }}>{p?.stats[s] ?? 0}</td>
                ))}
              </tr>
            );
          })}
          <tr style={{ borderTop: "2px solid var(--border)", fontWeight: 700 }}>
            <td style={{ padding: 6 }} colSpan={2}>Total</td>
            {shownStats.map((s) => {
              const met = !mins[s] || (totals[s] || 0) >= mins[s];
              return (
                <td key={s} style={{
                  padding: 6, textAlign: "right",
                  color: mins[s] ? (met ? "#2e7d32" : "#c62828") : undefined,
                }}>{totals[s] || 0}</td>
              );
            })}
          </tr>
          <tr style={{ color: "#1565c0" }}>
            <td style={{ padding: 6 }} colSpan={2}>Tier (÷10)</td>
            {shownStats.map((s) => (
              <td key={s} style={{ padding: 6, textAlign: "right" }}>{Math.floor((totals[s] || 0) / 10)}</td>
            ))}
          </tr>
          {minStats.length > 0 && (
            <tr style={{ color: "var(--muted)", fontSize: 12 }}>
              <td style={{ padding: 6 }} colSpan={2}>Minimum</td>
              {shownStats.map((s) => (
                <td key={s} style={{ padding: 6, textAlign: "right" }}>{mins[s] || "—"}</td>
              ))}
            </tr>
          )}
        </tbody>
      </table>
      <p style={{ color: "var(--muted)", fontSize: 12, marginTop: 10 }}>
        Best owned pieces per slot, max one exotic. ★ = masterworked. Minimums are best-effort
        (it maximizes those stats; a red total means it couldn't reach your minimum). Base armor
        stats only — mods and fragment bonuses aren't added in.
      </p>

      {saveMsg && (
        <p style={{ color: saveMsg.startsWith("✓") || saveMsg.startsWith("Saved") ? "#2e7d32" : "#c62828" }}>
          {saveMsg}
        </p>
      )}

      <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 14, marginTop: 16, marginBottom: 20, maxWidth: 640 }}>
        <strong>Save this set</strong>
        <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
          <input
            placeholder="Set name…" value={setName}
            onChange={(e) => setSetName(e.target.value)}
          />
          <select value={targetChar} onChange={(e) => setTargetChar(e.target.value)}>
            {classChars.length === 0 && <option value="">No {cls} character</option>}
            {classChars.map((c) => <option key={c.id} value={c.id}>{c.className} ✦{c.light}</option>)}
          </select>
          <button onClick={saveSet} disabled={busy || !setName.trim() || !setItems.length || !targetChar}>Save</button>
        </div>
        <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>
          Saves {setItems.length} piece(s) · Tier {armorSetTier(chosen)} for {cls}.
        </div>
      </div>

      <h2 style={{ marginTop: 8 }}>Saved armor sets</h2>
      {armorSets.length === 0 && <p style={{ color: "var(--muted)" }}>None yet.</p>}
      {armorSets.map((s) => (
        <div key={s.name} style={{
          display: "flex", alignItems: "center", gap: 12, border: "1px solid var(--border)",
          borderRadius: 8, padding: "8px 12px", marginBottom: 8, maxWidth: 640,
        }}>
          <strong style={{ flex: 1 }}>{s.name}</strong>
          <span style={{ color: "var(--muted)", fontSize: 13 }}>{s.className} · Tier {s.tier} · {s.items.length} pieces</span>
          <button onClick={() => applySet(s)} disabled={busy}>Apply</button>
          <button onClick={() => removeSet(s)} disabled={busy} style={{ color: "#c62828" }}>Delete</button>
        </div>
      ))}
    </div>
  );
}
