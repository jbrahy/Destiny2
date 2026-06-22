import { ActivityRec } from "./types";

export function buildContextOptions(
  activities: ActivityRec[],
): { value: string; label: string }[] {
  return [
    { value: "general-pve", label: "General (PvE)" },
    { value: "general-pvp", label: "General (PvP)" },
    ...activities.map((a) => ({ value: a.name, label: a.name })),
  ];
}
