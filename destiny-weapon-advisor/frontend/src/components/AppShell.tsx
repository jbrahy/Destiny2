import { useEffect, useState } from "react";
import { fetchStatus } from "../api";
import { Seo } from "../seo/Seo";
import { ActivitiesPage } from "./ActivitiesPage";
import { ArmorList } from "./ArmorList";
import { BuildsPage } from "./BuildsPage";
import { DismantlePage } from "./DismantlePage";
import { LoadoutsPage } from "./LoadoutsPage";
import { Login } from "./Login";
import { Nav, Section } from "./Nav";
import { PerksPage } from "./PerksPage";
import { RecommendPage } from "./RecommendPage";
import { SponsoredAds } from "./SponsoredAds";
import { WeaponGrid } from "./WeaponGrid";

export function AppShell() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [section, setSection] = useState<Section>("weapons");

  useEffect(() => {
    fetchStatus().then(setAuthed).catch(() => setAuthed(false));
  }, []);

  if (authed === null) return <div style={{ padding: 40 }}>Loading…</div>;
  if (!authed) return <Login />;

  return (
    <div style={{ fontFamily: "system-ui, sans-serif" }}>
      <Seo
        title="Destiny Advisor"
        description="Your personal Destiny 2 dashboard."
        path="/app"
        noindex
      />
      <Nav current={section} onChange={setSection} onLogout={() => setAuthed(false)} />
      <div style={{ padding: 24 }}>
        {section === "weapons" && (
          <>
            <h1 style={{ marginTop: 0 }}>Your Weapons</h1>
            <WeaponGrid />
          </>
        )}
        {section === "recommend" && <RecommendPage />}
        {section === "perks" && <PerksPage />}
        {section === "armor" && <ArmorList />}
        {section === "builds" && <BuildsPage />}
        {section === "activities" && <ActivitiesPage />}
        {section === "loadouts" && <LoadoutsPage />}
        {section === "dismantle" && <DismantlePage />}
      </div>
      <SponsoredAds section={section} />
    </div>
  );
}
