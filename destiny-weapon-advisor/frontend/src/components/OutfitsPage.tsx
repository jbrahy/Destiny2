import { useEffect, useState } from "react";
import { fetchOutfits, Outfit, OutfitItem } from "../api";
import { Icon } from "./Icon";

const ARMOR_SLOTS = ["Helmet", "Gauntlets", "Chest Armor", "Leg Armor", "Class Item"];
const AMMO_SLOTS = ["Primary", "Special", "Heavy"];

const EXOTIC_GOLD = "#caa000";

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

function OutfitCard({ outfit }: { outfit: Outfit }) {
  const exoticArmor = Object.values(outfit.armor).find((i) => i?.isExotic);
  const exoticWeapon = Object.values(outfit.weapons).find((i) => i?.isExotic);

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
    </div>
  );
}

export function OutfitsPage() {
  const [outfits, setOutfits] = useState<Outfit[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  function load() {
    setLoading(true);
    setError("");
    fetchOutfits()
      .then(setOutfits)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Outfits</h1>
      <p style={{ color: "var(--muted)", maxWidth: 720 }}>
        A complete, equippable loadout for every class and subclass you have a build for —
        the best armour and weapons you own, with exactly one exotic armour piece and one
        exotic weapon per outfit, same as Destiny enforces on your character.
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
            <OutfitCard key={`${o.className}|${o.subclass}`} outfit={o} />
          ))}
        </div>
      )}
    </div>
  );
}
