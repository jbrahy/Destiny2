import { Verdict } from "../types";

export interface FilterState {
  verdict: Verdict | "all";
  weaponType: string;
  search: string;
}

export function Filters({
  state, types, onChange,
}: {
  state: FilterState;
  types: string[];
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
    </div>
  );
}
