import { WeaponDto } from "../types";

export function WeaponDetail({ w, onClose }: { w: WeaponDto; onClose: () => void }) {
  return (
    <div style={{ border: "1px solid #ccc", borderRadius: 8, padding: 16, marginBottom: 16 }}>
      <button onClick={onClose} style={{ float: "right" }}>Close</button>
      <h2>{w.name}</h2>
      <p>{w.weaponType} · {w.element} · {w.location}</p>
      <p><strong>Verdict:</strong> {w.verdict}</p>
      <p><strong>Matched perks:</strong> {w.matchedPerks.join(", ") || "—"}</p>
      <p><strong>Why:</strong> {w.note || "No community note."}</p>
      {w.tags.length > 0 && <p><strong>Tags:</strong> {w.tags.join(", ")}</p>}
    </div>
  );
}
