import { ArmorPage } from "./ArmorPage";

export function BuildsPage() {
  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Builds</h1>
      <p style={{ color: "#666", maxWidth: 760 }}>
        Full class/subclass builds — your subclass setup (aspects, fragments, abilities) plus armor
        and weapons tuned for max power, and per-activity (campaign / strike / raid) recommendations
        — are the next step. For now, this is the <strong>armor stat optimizer</strong>, the gear
        half of a build.
      </p>
      <ArmorPage />
    </div>
  );
}
