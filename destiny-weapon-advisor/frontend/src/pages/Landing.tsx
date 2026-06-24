import { Link } from "react-router-dom";

export default function Landing() {
  return (
    <main style={{ padding: "48px 24px", maxWidth: 640 }}>
      <h1>Destiny 2 Weapon Advisor</h1>
      <p>
        Get personalized weapon recommendations for your Guardian. Connect your
        Bungie account to analyze your vault, identify god rolls, and build the
        perfect loadout for any activity.
      </p>
      <Link
        to="/app"
        style={{
          display: "inline-block",
          marginTop: 24,
          padding: "10px 24px",
          background: "var(--accent, #4a4aff)",
          color: "#fff",
          borderRadius: 4,
          fontWeight: 600,
          textDecoration: "none",
        }}
      >
        Open the App
      </Link>
    </main>
  );
}
