import { useEffect, useState } from "react";
import {
  DismantleCandidate, BatchPlan,
  fetchCharacters, fetchDismantlePreview, runDismantleSweep, undoDismantleSweep,
} from "../api";
import { Character } from "../types";

const BLOCK_LABEL: Record<string, string> = {
  locked: "Locked in-game",
  exotic: "Exotic",
  high_verdict: "High-value roll",
  equipped: "Equipped — cannot be swept",
};

export function DismantlePage() {
  const [characters, setCharacters] = useState<Character[]>([]);
  const [characterId, setCharacterId] = useState("");
  const [candidates, setCandidates] = useState<DismantleCandidate[]>([]);
  const [plan, setPlan] = useState<BatchPlan | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [overrides, setOverrides] = useState<Set<string>>(new Set());
  const [stagedCount, setStagedCount] = useState(0);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchCharacters()
      .then((chars) => {
        setCharacters(chars);
        if (chars.length) setCharacterId(chars[0].id);
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!characterId) return;
    fetchDismantlePreview(characterId)
      .then((res) => {
        setCandidates(res.candidates);
        setPlan(res.plan);
        setStagedCount(Object.keys(res.staged).length);
        // Junk-tagged start checked; engine suggestions start unchecked.
        setSelected(new Set(
          res.candidates.filter((c) => c.source === "tagged" && !c.blocked)
            .map((c) => c.instanceId),
        ));
      })
      .catch((e) => setError(String(e)));
  }, [characterId]);

  function toggle(set: Set<string>, id: string): Set<string> {
    const next = new Set(set);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  }

  // Cancelling an override must also drop the row from `selected` — a blocked,
  // non-overridden row is never usable, so it can't stay checked/selected.
  function toggleOverride(id: string) {
    setOverrides((prev) => {
      const next = toggle(prev, id);
      const cancelled = prev.has(id) && !next.has(id);
      if (cancelled) {
        setSelected((s) => {
          if (!s.has(id)) return s;
          const ns = new Set(s);
          ns.delete(id);
          return ns;
        });
      }
      return next;
    });
  }

  async function sweep() {
    setBusy(true);
    setError("");
    setInfo("");
    try {
      const res = await runDismantleSweep(
        characterId, [...selected], [...overrides],
      );
      setStagedCount(res.staged.length);
      if (res.deferred.length) {
        setInfo(`${res.staged.length} staged, ${res.deferred.length} deferred to the next batch.`);
      }
      const problems: string[] = [];
      if (res.rejected.length) {
        problems.push(`${res.rejected.length} rejected: ${res.rejected.map((r) => r.reason).join("; ")}`);
      }
      if (res.failed.length) {
        problems.push(`${res.failed.length} item(s) failed: ${res.failed.map((f) => f.error).join("; ")}`);
      }
      if (problems.length) setError(problems.join(" · "));
      const refreshed = await fetchDismantlePreview(characterId);
      setCandidates(refreshed.candidates);
      setPlan(refreshed.plan);
      setSelected(new Set());
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function undo() {
    setBusy(true);
    try {
      await undoDismantleSweep(characterId);
      setStagedCount(0);
      const refreshed = await fetchDismantlePreview(characterId);
      setCandidates(refreshed.candidates);
      setPlan(refreshed.plan);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  // The server stages per-bucket: an item only fits if its OWN bucket has room,
  // so the headline number must sum per-bucket minima, not a flat total.
  let fitting = 0;
  if (plan) {
    const selectedByBucket: Record<string, number> = {};
    for (const c of candidates) {
      if (selected.has(c.instanceId)) {
        selectedByBucket[c.bucketHash] = (selectedByBucket[c.bucketHash] ?? 0) + 1;
      }
    }
    for (const [bucketHash, count] of Object.entries(selectedByBucket)) {
      fitting += Math.min(count, plan.perBucket[bucketHash]?.free ?? 0);
    }
  }

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Dismantle Sweep</h1>
      <p style={{ color: "var(--muted)", maxWidth: 680 }}>
        Bungie's API cannot dismantle items. This moves what you pick onto one
        character and unlocks it, so you can dismantle the whole batch from a
        single screen in-game.
      </p>

      <label>
        Character{" "}
        <select value={characterId} onChange={(e) => setCharacterId(e.target.value)}>
          {characters.map((c) => (
            <option key={c.id} value={c.id}>
              {c.className} — {c.light}
            </option>
          ))}
        </select>
      </label>

      {stagedCount > 0 && (
        <div style={{ margin: "16px 0", padding: 12, border: "1px solid var(--border)", borderRadius: 6 }}>
          <strong>{stagedCount} weapon(s) staged.</strong> Dismantle them in-game,
          then run the next batch.{" "}
          <button onClick={undo} disabled={busy}>Undo sweep</button>
        </div>
      )}

      {plan && (
        <p style={{ color: "var(--muted)" }}>
          {selected.size} selected · about {Math.min(selected.size, fitting)} fit this batch ·{" "}
          {Object.entries(plan.perBucket).map(([k, b]) => `${b.name} ${b.free} free`).join(" · ")}
        </p>
      )}

      {info && <p style={{ color: "var(--muted)" }}>{info}</p>}
      {error && <p style={{ color: "#c62828" }}>{error}</p>}

      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ textAlign: "left", color: "var(--muted)" }}>
            <th /><th>Weapon</th><th>Power</th><th>Verdict</th><th>Why</th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((c) => {
            const overridden = overrides.has(c.instanceId);
            const usable = !c.blocked || (c.overridable && overridden);
            return (
              <tr key={c.instanceId} style={{
                opacity: usable ? 1 : 0.45,
                borderTop: "1px solid var(--border)",
              }}>
                <td>
                  <input
                    type="checkbox"
                    disabled={!usable}
                    checked={selected.has(c.instanceId)}
                    onChange={() => setSelected(toggle(selected, c.instanceId))}
                  />
                </td>
                <td>
                  {c.icon && <img src={`https://www.bungie.net${c.icon}`} alt="" width={28} height={28} />}
                  {" "}{c.name}
                </td>
                <td>{c.power}</td>
                <td>{c.verdict}</td>
                <td>
                  {c.blocked ? (
                    <>
                      <span style={{ color: "#c62828", fontWeight: 700 }}>
                        {BLOCK_LABEL[c.blocked] ?? c.blocked}
                      </span>
                      {c.overridable && (
                        <button
                          style={{ marginLeft: 8 }}
                          onClick={() => toggleOverride(c.instanceId)}
                        >
                          {overridden ? "Cancel override" : "Override"}
                        </button>
                      )}
                    </>
                  ) : c.reason}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {candidates.length === 0 && (
        <p style={{ color: "var(--muted)" }}>
          Nothing to sweep. Tag weapons "junk" on the Weapons tab to queue them here.
        </p>
      )}

      <button
        onClick={sweep}
        disabled={busy || selected.size === 0 || !characterId}
        style={{ marginTop: 16, padding: "8px 18px", fontWeight: 700 }}
      >
        {busy ? "Staging…" : `Stage ${selected.size} weapon(s)`}
      </button>
    </div>
  );
}
