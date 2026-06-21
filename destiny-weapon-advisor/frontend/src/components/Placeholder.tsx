export function Placeholder({ title, blurb }: { title: string; blurb: string }) {
  return (
    <div style={{ padding: 40, textAlign: "center", color: "#666" }}>
      <h2>{title}</h2>
      <p>{blurb}</p>
      <p style={{ fontSize: 13, color: "#999" }}>Coming soon.</p>
    </div>
  );
}
