import { useEffect, useState } from "react";
import { fetchStatus } from "./api";
import { Login } from "./components/Login";
import { Nav, Section } from "./components/Nav";
import { PerksPage } from "./components/PerksPage";
import { Placeholder } from "./components/Placeholder";
import { WeaponGrid } from "./components/WeaponGrid";

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [section, setSection] = useState<Section>("weapons");

  useEffect(() => {
    fetchStatus().then(setAuthed).catch(() => setAuthed(false));
  }, []);

  if (authed === null) return <div style={{ padding: 40 }}>Loading…</div>;
  if (!authed) return <Login />;

  return (
    <div style={{ fontFamily: "system-ui, sans-serif" }}>
      <Nav current={section} onChange={setSection} />
      <div style={{ padding: 24 }}>
        {section === "weapons" && (
          <>
            <h1 style={{ marginTop: 0 }}>Your Weapons</h1>
            <WeaponGrid />
          </>
        )}
        {section === "perks" && <PerksPage />}
        {section === "armor" && (
          <Placeholder
            title="Armor Optimizer"
            blurb="Read your armor and find the best stat-tier loadouts for each character."
          />
        )}
        {section === "builds" && (
          <Placeholder
            title="Subclass Builds"
            blurb="Recommended super, aspects, fragments, and abilities per class and subclass."
          />
        )}
      </div>
    </div>
  );
}
