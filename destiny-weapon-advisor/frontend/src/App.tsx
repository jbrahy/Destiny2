import { useEffect, useState } from "react";
import { fetchStatus } from "./api";
import { Login } from "./components/Login";

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(null);

  useEffect(() => {
    fetchStatus().then(setAuthed).catch(() => setAuthed(false));
  }, []);

  if (authed === null) return <div style={{ padding: 40 }}>Loading…</div>;
  if (!authed) return <Login />;
  return <div style={{ padding: 40 }}>Authenticated. Weapon view added in Task 9.</div>;
}
