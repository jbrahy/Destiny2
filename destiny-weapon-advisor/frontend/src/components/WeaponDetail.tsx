import { useState } from "react";
import { moveItem } from "../api";
import { Character, WeaponDto } from "../types";
import { Icon } from "./Icon";
import { TagSelect } from "./TagSelect";

function StatBar({ name, value }: { name: string; value: number }) {
  // Only the 0–100 stats (Range, Stability, Handling…) get a meaningful bar.
  // Absolute stats (RPM, Magazine, Charge Time…) just show the number.
  const showBar = value >= 0 && value <= 100;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
      <span style={{ width: 130, fontSize: 12, color: "var(--muted)" }}>{name}</span>
      {showBar ? (
        <div style={{ flex: 1, background: "var(--track)", borderRadius: 3, height: 10 }}>
          <div style={{ width: `${value}%`, background: "#1565c0", height: 10, borderRadius: 3 }} />
        </div>
      ) : (
        <div style={{ flex: 1 }} />
      )}
      <span style={{ width: 40, textAlign: "right", fontSize: 12 }}>{value}</span>
    </div>
  );
}

export function WeaponDetail({
  w, characters, tag, onTag, onClose, onMoved,
}: {
  w: WeaponDto;
  characters: Character[];
  tag: string;
  onTag: (t: string) => void;
  onClose: () => void;
  onMoved: () => void;
}) {
  const meta = [w.weaponType, w.element, w.ammoType, w.location].filter(Boolean).join(" · ");
  const statEntries = Object.entries(w.stats);
  const [equip, setEquip] = useState(false);
  const [moving, setMoving] = useState(false);
  const [moveMsg, setMoveMsg] = useState<string | null>(null);

  async function doMove(target: Character) {
    const ok = window.confirm(
      `Move "${w.name}" to your ${target.className}${equip ? " and equip it" : ""}?`,
    );
    if (!ok) return;
    setMoving(true);
    setMoveMsg(null);
    try {
      await moveItem({
        instanceId: w.instanceId, itemHash: w.itemHash, targetCharacterId: target.id, equip,
      });
      setMoveMsg(`✓ Moved to ${target.className}${equip ? " and equipped" : ""}.`);
      onMoved();
    } catch (e) {
      setMoveMsg(`✗ ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setMoving(false);
    }
  }

  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 16, marginBottom: 16 }}>
      <button onClick={onClose} style={{ float: "right" }}>Close</button>
      <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 8 }}>
        <Icon path={w.icon} size={56} alt={w.name} />
        <div>
          <h2 style={{ margin: "0 0 2px" }}>{w.name}</h2>
          <p style={{ margin: 0, color: "var(--muted)" }}>{meta}{w.isMasterworked ? " · ★ Masterworked" : ""}</p>
        </div>
      </div>
      <p style={{ margin: "0 0 8px" }}>
        {w.power > 0 && <strong>✦ {w.power} Power</strong>}
        {w.frame && <span> · {w.frame}</span>}
      </p>

      <div style={{ marginBottom: 10 }}>
        <strong style={{ fontSize: 13, marginRight: 6 }}>Tag:</strong>
        <TagSelect value={tag} onChange={onTag} />
      </div>

      {characters.length > 0 && (
        <div style={{ background: "var(--panel2)", borderRadius: 6, padding: "8px 10px", marginBottom: 10 }}>
          <strong style={{ fontSize: 13 }}>Move to: </strong>
          {characters.map((c) => (
            <button
              key={c.id}
              disabled={moving || w.location === c.className}
              onClick={() => doMove(c)}
              style={{ margin: "0 4px", padding: "4px 10px" }}
            >
              {c.className} {c.current ? "(current)" : ""}
            </button>
          ))}
          <label style={{ marginLeft: 8, fontSize: 13 }}>
            <input type="checkbox" checked={equip} onChange={(e) => setEquip(e.target.checked)} /> equip
          </label>
          {moveMsg && (
            <div style={{ marginTop: 6, fontSize: 13, color: moveMsg.startsWith("✓") ? "#2e7d32" : "#c62828" }}>
              {moveMsg}
            </div>
          )}
        </div>
      )}

      <p style={{ margin: "0 0 4px" }}><strong>Verdict:</strong> {w.verdict.replace("_", " ")}</p>
      {w.tags.length > 0 && <p style={{ margin: "0 0 4px" }}><strong>Best for:</strong> {w.tags.join(", ")}</p>}

      {w.ratedPerks.length > 0 ? (
        <>
          <h3 style={{ margin: "12px 0 4px" }}>Why (rated perks)</h3>
          {w.ratedPerks.map((p) => (
            <div key={p.name} style={{ marginBottom: 3 }}>
              <strong>{p.rating}</strong> · {p.name}
              {p.reason && <span style={{ color: "var(--muted)" }}> — {p.reason}</span>}
            </div>
          ))}
        </>
      ) : (
        <p style={{ margin: "8px 0 4px", color: "var(--muted)" }}>
          None of this weapon's perks are rated yet — add ratings on the Perks tab.
        </p>
      )}

      {w.perkNames.length > 0 && (
        <>
          <h3 style={{ margin: "12px 0 4px" }}>Roll</h3>
          <p style={{ margin: 0 }}>{w.perkNames.join(" · ")}</p>
        </>
      )}

      {statEntries.length > 0 && (
        <>
          <h3 style={{ margin: "12px 0 6px" }}>Stats</h3>
          {statEntries.map(([name, value]) => (
            <StatBar key={name} name={name} value={value} />
          ))}
        </>
      )}
    </div>
  );
}
