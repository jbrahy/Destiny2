import { ICON_BASE } from "../visual";

export function Icon({
  path, size = 36, alt = "", border,
}: {
  path?: string;
  size?: number;
  alt?: string;
  border?: string;
}) {
  const style = {
    width: size, height: size, borderRadius: 4, flexShrink: 0,
    border: border ? `2px solid ${border}` : "1px solid var(--border)", boxSizing: "border-box" as const,
    objectFit: "cover" as const, background: "#1b2838",
  };
  if (!path) return <div style={style} />;
  return <img src={ICON_BASE + path} width={size} height={size} alt={alt} loading="lazy" style={style} />;
}
