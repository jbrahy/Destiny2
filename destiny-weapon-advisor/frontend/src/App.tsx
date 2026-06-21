import { useEffect, useState } from "react";
import { fetchStatus } from "./api";
import { Login } from "./components/Login";
import { WeaponGrid } from "./components/WeaponGrid";

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(null);

  useEffect(() => {
    fetchStatus().then(setAuthed).catch(() => setAuthed(false));
  }, []);

  if (authed === null) return <div style={{ padding: 40 }}>Loading…</div>;
  if (!authed) return <Login />;
  return (
    <div style={{ padding: 24, fontFamily: "system-ui, sans-serif" }}>
      <h1>Your Weapons</h1>
      <WeaponGrid />
    </div>
  );
}
