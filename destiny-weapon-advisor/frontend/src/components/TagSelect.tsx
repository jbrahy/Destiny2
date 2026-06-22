import { TAGS, TAG_COLOR } from "../visual";

export function TagSelect({ value, onChange }: { value: string; onChange: (t: string) => void }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      style={{ color: TAG_COLOR[value] || "#333", fontWeight: value ? 700 : 400, padding: "3px 6px" }}
    >
      <option value="">— tag —</option>
      {TAGS.map((t) => <option key={t} value={t}>{t}</option>)}
    </select>
  );
}

export function TagChip({ tag }: { tag?: string }) {
  if (!tag) return null;
  return (
    <span style={{
      fontSize: 11, fontWeight: 700, color: "#fff", background: TAG_COLOR[tag] || "#666",
      borderRadius: 4, padding: "1px 6px",
    }}>
      {tag}
    </span>
  );
}
