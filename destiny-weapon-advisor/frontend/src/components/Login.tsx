import { loginUrl } from "../api";

export function Login() {
  return (
    <div style={{ padding: 40, textAlign: "center" }}>
      <h1>Destiny 2 Weapon Advisor</h1>
      <p>Log in with your Bungie account to analyze your weapons.</p>
      <a href={loginUrl}>
        <button style={{ fontSize: 18, padding: "10px 24px" }}>Login with Bungie</button>
      </a>
    </div>
  );
}
