import { useEffect, useState } from "react";
import {
  applyOutfit, fetchCharacters, fetchOutfits, Outfit, OutfitItem, OutfitPlanStep,
} from "../api";
import { Character, MoveResult } from "../types";
import { Icon } from "./Icon";

const ARMOR_SLOTS = ["Helmet", "Gauntlets", "Chest Armor", "Leg Armor", "Class Item"];
const AMMO_SLOTS = ["Primary", "Special", "Heavy"];

const EXOTIC_GOLD = "#caa000";
const RED = "#c62828";
const GREEN = "#2e7d32";

const ACTION_COLOR: Record<OutfitPlanStep["action"], string> = {
  move: "var(--accent)",
  skip: "var(--muted)",
  blocked: RED,
};

function ItemRow({ slot, item, kind }: { slot: string; item: OutfitItem; kind: "armor" | "weapon" }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 0" }}>
      <span style={{ width: 92, flexShrink: 0, fontSize: 11, color: "var(--muted)" }}>{slot}</span>
      {item ? (
        <>
          <Icon path={item.icon} size={28} alt={item.name} border={item.isExotic ? EXOTIC_GOLD : undefined} />
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{ fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {item.name}
              {item.isExotic && <span style={{ color: EXOTIC_GOLD, fontWeight: 700 }}> ◆ Exotic</span>}
            </div>
            {kind === "weapon" && item.matchedPerks && item.matchedPerks.length > 0 && (
              <div style={{ fontSize: 11, color: "var(--muted)" }}>{item.matchedPerks.join(" · ")}</div>
            )}
            {kind === "armor" && item.setName && (
              <div
                style={{ fontSize: 11, color: "var(--muted)" }}
                title={(item.setBonuses ?? []).map((b) => `${b.count}pc ${b.name}: ${b.description}`).join("\n")}
              >
                {item.setName}
                {item.focus !== undefined ? ` · focus ${item.focus}` : ""}
              </div>
            )}
          </div>
        </>
      ) : (
        <span style={{ fontSize: 12, color: "var(--muted)", fontStyle: "italic" }}>— none owned —</span>
      )}
    </div>
  );
}

/** The confirm step. Shows what will happen to each item BEFORE anything moves,
 *  because "equipped on your other Warlock" is the normal case, not an edge one,
 *  and it is far better learned here than from a wall of red afterwards. */
function ConfirmPanel({
  plan, busy, onCancel, onConfirm,
}: {
  plan: OutfitPlanStep[];
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const movable = plan.filter((p) => p.action === "move").length;
  const blocked = plan.filter((p) => p.action === "blocked").length;

  return (
    <div style={{
      marginTop: 10, padding: 10, borderRadius: 6,
      border: "1px solid var(--border)", background: "var(--bg, rgba(0,0,0,0.15))",
    }}>
      <div style={{ fontSize: 12, marginBottom: 8 }}>
        <strong>{movable}</strong> to transfer and equip
        {blocked > 0 && <>, <strong style={{ color: RED }}>{blocked}</strong> blocked</>}
      </div>
      {plan.map((p) => (
        <div key={p.instanceId} style={{ fontSize: 11, display: "flex", gap: 6, padding: "1px 0" }}>
          <span style={{ width: 84, flexShrink: 0, color: "var(--muted)" }}>{p.slot}</span>
          <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {p.name}
          </span>
          <span style={{ color: ACTION_COLOR[p.action], flexShrink: 0 }} title={p.reason}>
            {p.action}
          </span>
        </div>
      ))}
      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
        <button onClick={onConfirm} disabled={busy || movable === 0}>
          {busy ? "Equipping…" : `Equip ${movable} item${movable === 1 ? "" : "s"}`}
        </button>
        <button onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
      {movable === 0 && (
        <p style={{ fontSize: 11, color: "var(--muted)", margin: "8px 0 0" }}>
          Nothing to move — everything is either already equipped or blocked.
        </p>
      )}
    </div>
  );
}

function ResultsPanel({ plan, results }: { plan: OutfitPlanStep[]; results: MoveResult[] }) {
  const nameOf = (id: string) => plan.find((p) => p.instanceId === id)?.name ?? id;
  const failed = results.filter((r) => !r.ok);
  return (
    <div style={{ marginTop: 10, fontSize: 11 }}>
      <div style={{ marginBottom: 6, color: failed.length ? RED : GREEN, fontWeight: 700 }}>
        {results.length - failed.length}/{results.length} equipped
        {failed.length > 0 && ` · ${failed.length} failed`}
      </div>
      {results.map((r) => (
        <div key={r.instanceId} style={{ display: "flex", gap: 6, padding: "1px 0" }}>
          <span style={{ color: r.ok ? GREEN : RED, flexShrink: 0 }}>{r.ok ? "✓" : "✕"}</span>
          <span style={{ flex: 1, minWidth: 0 }}>{nameOf(r.instanceId)}</span>
          {r.error && <span style={{ color: RED, flex: 2, minWidth: 0 }}>{r.error}</span>}
        </div>
      ))}
    </div>
  );
}

function OutfitCard({ outfit, characters }: { outfit: Outfit; characters: Character[] }) {
  const exoticArmor = Object.values(outfit.armor).find((i) => i?.isExotic);
  const exoticWeapon = Object.values(outfit.weapons).find((i) => i?.isExotic);

  const mine = characters.filter((c) => c.className === outfit.className);
  const [target, setTarget] = useState("");
  const [plan, setPlan] = useState<OutfitPlanStep[] | null>(null);
  const [results, setResults] = useState<MoveResult[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const characterId = target || mine[0]?.id || "";

  // Every response is checked against the character it was requested for. A
  // plan computed for one character must never be confirmed against another —
  // the user would review "5 blocked" for Warlock A and land all 8 on Warlock B.
  function run(dryRun: boolean) {
    const requestedFor = characterId;
    setBusy(true); setError("");
    // The wet run keeps the plan on screen so the confirm panel can show
    // "Equipping…" rather than vanishing mid-request.
    if (dryRun) { setPlan(null); setResults(null); }
    applyOutfit(outfit.className, outfit.subclass, requestedFor, dryRun)
      .then((r) => {
        if (requestedFor !== characterId) return;   // picker moved — discard
        setPlan(r.plan);
        if (!dryRun) setResults(r.results);
      })
      .catch((e) => { if (requestedFor === characterId) setError(String(e)); })
      .finally(() => setBusy(false));
  }

  return (
    <div style={{
      border: "1px solid var(--border)", borderRadius: 8, padding: 14, background: "var(--panel)",
    }}>
      <h3 style={{ margin: "0 0 2px" }}>{outfit.className} · {outfit.subclass}</h3>
      <p style={{ margin: "0 0 8px", fontSize: 12, color: "var(--muted)" }}>
        prioritising {outfit.statPriority.join(", ")}
      </p>
      <p style={{ margin: "0 0 10px", fontSize: 12 }}>
        <strong>Exotics: </strong>
        <span style={{ color: exoticArmor ? EXOTIC_GOLD : "var(--muted)" }}>
          {exoticArmor ? exoticArmor.name : "none equipped"}
        </span>
        {" · "}
        <span style={{ color: exoticWeapon ? EXOTIC_GOLD : "var(--muted)" }}>
          {exoticWeapon ? exoticWeapon.name : "none equipped"}
        </span>
      </p>
      {ARMOR_SLOTS.map((slot) => (
        <ItemRow key={slot} slot={slot} item={outfit.armor[slot] ?? null} kind="armor" />
      ))}
      <div style={{ borderTop: "1px solid var(--border)", margin: "8px 0" }} />
      {AMMO_SLOTS.map((slot) => (
        <ItemRow key={slot} slot={slot} item={outfit.weapons[slot] ?? null} kind="weapon" />
      ))}

      <div style={{ borderTop: "1px solid var(--border)", margin: "10px 0 8px" }} />
      {mine.length === 0 ? (
        <p style={{ fontSize: 11, color: "var(--muted)", margin: 0 }}>
          No {outfit.className} character on this account.
        </p>
      ) : (
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          {/* The picker always renders, even with one character: the button's
              target is the most consequential thing about it, and a control
              that appears only sometimes is one you stop reading. */}
          <select
            value={characterId}
            disabled={busy}
            onChange={(e) => { setTarget(e.target.value); setPlan(null); setResults(null); }}
            style={{ fontSize: 12, maxWidth: 180 }}
            aria-label={`Character to equip this ${outfit.className} outfit on`}
          >
            {mine.map((c) => (
              <option key={c.id} value={c.id}>
                {c.className} ✦{c.light}{c.current ? " (current)" : ""}
              </option>
            ))}
          </select>
          <button onClick={() => run(true)} disabled={busy || !characterId}>
            {busy && !plan ? "Checking…" : "Equip"}
          </button>
        </div>
      )}

      {error && <p style={{ color: RED, fontSize: 11, margin: "8px 0 0" }}>{error}</p>}

      {plan && !results && (
        <ConfirmPanel
          plan={plan}
          busy={busy}
          onCancel={() => setPlan(null)}
          onConfirm={() => run(false)}
        />
      )}
      {results && plan && <ResultsPanel plan={plan} results={results} />}
    </div>
  );
}

export function OutfitsPage() {
  const [outfits, setOutfits] = useState<Outfit[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  function load() {
    setLoading(true);
    setError("");
    Promise.all([fetchOutfits(), fetchCharacters()])
      .then(([o, c]) => { setOutfits(o); setCharacters(c); })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Outfits</h1>
      <p style={{ color: "var(--muted)", maxWidth: 720 }}>
        The best loadout you can field for every class and subclass you have a build for,
        from armor and weapons you already own. Each outfit spends at most one exotic armor
        piece and one exotic weapon — the same limit Destiny enforces on your character.
        A slot you own nothing for is left empty rather than filled with a guess.
      </p>

      <button onClick={load} disabled={loading} style={{ marginBottom: 16 }}>
        {loading ? "Generating…" : "Generate outfits"}
      </button>

      {error && <p style={{ color: "#c62828" }}>{error}</p>}
      {loading && <p style={{ color: "var(--muted)" }}>Loading…</p>}

      {!loading && !error && outfits.length === 0 && (
        <p style={{ color: "var(--muted)" }}>
          No outfits yet — load your inventory on the Weapons tab first.
        </p>
      )}

      {outfits.length > 0 && (
        <div style={{
          display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
        }}>
          {outfits.map((o) => (
            <OutfitCard key={`${o.className}|${o.subclass}`} outfit={o} characters={characters} />
          ))}
        </div>
      )}
    </div>
  );
}
