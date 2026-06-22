import { describe, expect, it } from "vitest";
import { VERDICT_LABEL } from "./types";

describe("VERDICT_LABEL", () => {
  it("labels the masterwork verdict", () => {
    expect(VERDICT_LABEL.masterwork).toBe("Masterwork → God Roll");
  });

  it("has a label for every verdict and no 'upgrade' key", () => {
    expect(Object.keys(VERDICT_LABEL).sort()).toEqual(
      ["dismantle", "god_roll", "good", "masterwork", "no_data"],
    );
  });
});
