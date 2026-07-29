import { Verdict } from "../types";
import { elementColor } from "../visual";

export type SortKey =
  | "power_desc" | "power_asc" | "verdict" | "name" | "type" | "element";

export interface FilterState {
  verdict: Verdict | "all";
  weaponType: string;
  element: string;
  search: string;
  sort: SortKey;
}

export function Filters({
  state, types, elements, onChange,
}: {
  state: FilterState;
  types: string[];
  elements: string[];
  onChange: (s: FilterState) => void;
}) {
  return (
    <div style={{ display: "flex", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
      <input
        placeholder="Search… e.g. type:pulse element:void is:masterwork perk:outlaw"
        value={state.search}
        onChange={(e) => onChange({ ...state, search: e.target.value })}
        style={{ minWidth: 320 }}
      />
      <select
        value={state.verdict}
        onChange={(e) => onChange({ ...state, verdict: e.target.value as FilterState["verdict"] })}
      >
        <option value="all">All verdicts</option>
        <option value="god_roll">God Roll</option>
        <option value="masterwork">Masterwork → God Roll</option>
        <option value="good">Good</option>
        <option value="no_data">No Data</option>
        <option value="dismantle">Dismantle</option>
      </select>
      <select
        value={state.weaponType}
        onChange={(e) => onChange({ ...state, weaponType: e.target.value })}
      >
        <option value="all">All types</option>
        {types.map((t) => (
          <option key={t} value={t}>{t}</option>
        ))}
      </select>
      <select
        value={state.element}
        onChange={(e) => onChange({ ...state, element: e.target.value })}
        title="Filter by damage type"
        style={{
          color: state.element === "all" ? "var(--text)" : elementColor(state.element),
          fontWeight: state.element === "all" ? 400 : 700,
        }}
      >
        <option value="all">All damage types</option>
        {elements.map((el) => (
          <option key={el} value={el}>{el}</option>
        ))}
      </select>
      <select
        value={state.sort}
        onChange={(e) => onChange({ ...state, sort: e.target.value as SortKey })}
        title="Sort weapons"
      >
        <option value="power_desc">Power: High → Low</option>
        <option value="power_asc">Power: Low → High</option>
        <option value="verdict">Verdict (best first)</option>
        <option value="name">Name (A–Z)</option>
        <option value="type">Type (A–Z)</option>
        <option value="element">Element (A–Z)</option>
      </select>
    </div>
  );
}
