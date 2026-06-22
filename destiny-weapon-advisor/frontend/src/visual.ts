export const ICON_BASE = "https://www.bungie.net";

export const ELEMENT_COLOR: Record<string, string> = {
  Kinetic: "#d9d9d9",
  Arc: "#79e7ff",
  Solar: "#f0631e",
  Void: "#b184c5",
  Stasis: "#4d6fff",
  Strand: "#35e366",
  Unknown: "#999",
};

export function elementColor(element: string): string {
  return ELEMENT_COLOR[element] || ELEMENT_COLOR.Unknown;
}
