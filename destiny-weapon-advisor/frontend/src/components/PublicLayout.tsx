import { Link, Outlet } from "react-router-dom";
import { SponsoredAds } from "./SponsoredAds";

export function PublicLayout() {
  return (
    <div style={{ fontFamily: "system-ui, sans-serif" }}>
      <header
        style={{
          position: "sticky",
          top: 0,
          zIndex: 10,
          display: "flex",
          alignItems: "center",
          gap: 18,
          padding: "12px 24px",
          background: "rgba(10, 14, 22, 0.82)",
          backdropFilter: "blur(10px)",
          borderBottom: "1px solid var(--border, #333)",
        }}
      >
        <Link
          to="/"
          style={{
            fontFamily: "'Chakra Petch', sans-serif",
            fontSize: 17,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            whiteSpace: "nowrap",
            color: "inherit",
            textDecoration: "none",
          }}
        >
          <span style={{ color: "var(--accent, #4a4aff)" }}>◆</span>{" "}
          Destiny&nbsp;2{" "}
          <span style={{ color: "var(--accent, #4a4aff)" }}>Advisor</span>
        </Link>
        <nav style={{ display: "flex", gap: 16 }}>
          <Link to="/" style={{ color: "var(--muted, #aaa)", textDecoration: "none" }}>
            Home
          </Link>
          <Link to="/app" style={{ color: "var(--muted, #aaa)", textDecoration: "none" }}>
            Open the App
          </Link>
        </nav>
      </header>

      <Outlet />

      <footer
        style={{
          marginTop: 48,
          padding: "24px",
          borderTop: "1px solid var(--border, #333)",
          color: "var(--muted, #aaa)",
          fontSize: 12,
          textAlign: "center",
        }}
      >
        Destiny 2 Weapon Advisor — not affiliated with Bungie, Inc.
      </footer>

      <SponsoredAds section="public" />
    </div>
  );
}
