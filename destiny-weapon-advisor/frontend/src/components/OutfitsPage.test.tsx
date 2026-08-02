/** OutfitsPage state machine.
 *
 * Both bugs this page has shipped were in its state, not its rendering, and
 * both could equip the wrong items onto a real Destiny account:
 *
 *   1. Outfits and the focus that produced them were separate state, so
 *      changing the focus armed every Equip button with the new focus while
 *      the cards still showed the old outfits.
 *   2. Changing the character mid-preview let a plan computed for character A
 *      be confirmed against character B.
 *
 * These are the regression tests for both.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const fetchOutfits = vi.fn();
const fetchCharacters = vi.fn();
const applyOutfit = vi.fn();

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,   // keep the real ARMOR_STATS / MAX_FOCUS the picker renders from
    fetchOutfits: (...a: unknown[]) => fetchOutfits(...a),
    fetchCharacters: (...a: unknown[]) => fetchCharacters(...a),
    applyOutfit: (...a: unknown[]) => applyOutfit(...a),
  };
});

const { OutfitsPage } = await import("./OutfitsPage");

function item(name: string) {
  return { instanceId: `${name}-id`, name, icon: "", isExotic: false, matchedPerks: [] };
}

function outfit(className: string, subclass: string, helmet: string, statPriority: string[]) {
  return {
    className, subclass, statPriority, build: {},
    armor: {
      "Helmet": item(helmet), "Gauntlets": null, "Chest Armor": null,
      "Leg Armor": null, "Class Item": null,
    },
    weapons: { Primary: null, Special: null, Heavy: null },
  };
}

const WARLOCK_A = { id: "wl-a", className: "Warlock", light: 2000, lastPlayed: "2", current: true };
const WARLOCK_B = { id: "wl-b", className: "Warlock", light: 1990, lastPlayed: "1", current: false };

const SEEDED = [outfit("Warlock", "Solar", "Grenade Helm", ["Grenade"])];
const FOCUSED = [outfit("Warlock", "Solar", "Super Helm", ["Super"])];

beforeEach(() => {
  fetchOutfits.mockReset().mockResolvedValue(SEEDED);
  fetchCharacters.mockReset().mockResolvedValue([WARLOCK_A, WARLOCK_B]);
  applyOutfit.mockReset();
});

afterEach(cleanup);

async function renderLoaded() {
  render(<OutfitsPage />);
  await screen.findByText("Grenade Helm");
}

describe("stat focus", () => {
  it("sends the chosen focus to the backend", async () => {
    await renderLoaded();
    await userEvent.click(screen.getByRole("button", { name: "Super" }));
    await waitFor(() => expect(fetchOutfits).toHaveBeenLastCalledWith(["Super"]));
  });

  it("never shows outfits from one focus while a different focus is armed", async () => {
    // THE REGRESSION. Second fetch hangs, so we sit in the exact window where
    // the old cards used to stay on screen with the new focus already wired
    // into their Equip buttons.
    await renderLoaded();
    fetchOutfits.mockReturnValue(new Promise(() => {}));

    await userEvent.click(screen.getByRole("button", { name: "Super" }));

    await waitFor(() => expect(screen.queryByText("Grenade Helm")).toBeNull());
    expect(screen.queryByRole("button", { name: "Equip" })).toBeNull();
  });

  it("does not leave stale outfits on screen when the refetch fails", async () => {
    // The failure made the mismatch permanent: loading went false, nothing
    // replaced the outfits, and every Equip button stayed armed with the new
    // focus over the old cards.
    await renderLoaded();
    fetchOutfits.mockRejectedValue(new Error("Load your inventory first."));

    await userEvent.click(screen.getByRole("button", { name: "Super" }));

    await screen.findByText(/Load your inventory first/);
    expect(screen.queryByText("Grenade Helm")).toBeNull();
    expect(screen.queryByRole("button", { name: "Equip" })).toBeNull();
  });

  it("equips using the focus that produced the outfits on screen", async () => {
    await renderLoaded();
    fetchOutfits.mockResolvedValue(FOCUSED);
    await userEvent.click(screen.getByRole("button", { name: "Super" }));
    await screen.findByText("Super Helm");

    applyOutfit.mockResolvedValue({ plan: [], results: [] });
    await userEvent.click(screen.getByRole("button", { name: "Equip" }));

    await waitFor(() => expect(applyOutfit).toHaveBeenCalledWith(
      "Warlock", "Solar", "wl-a", true, ["Super"],
    ));
  });

  it("refuses a fourth stat rather than silently dropping one", async () => {
    await renderLoaded();
    for (const s of ["Health", "Melee", "Grenade"]) {
      await userEvent.click(screen.getByRole("button", { name: s }));
      await screen.findByText("Grenade Helm");   // wait out each refetch
    }
    await userEvent.click(screen.getByRole("button", { name: "Super" }));

    await screen.findByText(/Up to 3 stats/);
    expect(fetchOutfits).toHaveBeenLastCalledWith(["Health", "Melee", "Grenade"]);
  });

  it("says that no selection means the seeded priorities, not no priority", async () => {
    await renderLoaded();
    expect(screen.getByText(/each outfit uses its own build/)).toBeTruthy();
  });
});

describe("the equip confirm", () => {
  const PLAN = [{
    slot: "Helmet", instanceId: "Grenade Helm-id", itemHash: 1,
    name: "Grenade Helm", isExotic: false, action: "move" as const, reason: "",
  }];

  it("shows the plan before anything moves", async () => {
    await renderLoaded();
    applyOutfit.mockResolvedValue({ plan: PLAN, results: [] });

    await userEvent.click(screen.getByRole("button", { name: "Equip" }));

    await screen.findByRole("button", { name: "Equip 1 item" });
    expect(applyOutfit).toHaveBeenCalledWith("Warlock", "Solar", "wl-a", true, []);
  });

  it("previews and equips against the character currently selected", async () => {
    // THE OTHER REGRESSION was confirming a plan computed for character A
    // against character B. Two layers stop it now: the picker is locked while
    // a request is in flight (tested below), and a response whose character no
    // longer matches is discarded. This asserts the invariant they exist for —
    // the panel on screen always belongs to the selected character.
    await renderLoaded();
    applyOutfit.mockResolvedValue({ plan: PLAN, results: [] });

    await userEvent.selectOptions(screen.getByLabelText(/Character to equip/), "wl-b");
    await userEvent.click(screen.getByRole("button", { name: "Equip" }));
    await screen.findByRole("button", { name: "Equip 1 item" });

    expect(applyOutfit).toHaveBeenLastCalledWith("Warlock", "Solar", "wl-b", true, []);

    applyOutfit.mockResolvedValue({ plan: PLAN, results: [{ instanceId: PLAN[0].instanceId, ok: true }] });
    await userEvent.click(screen.getByRole("button", { name: "Equip 1 item" }));

    await screen.findByText(/1\/1 equipped/);
    expect(applyOutfit).toHaveBeenLastCalledWith("Warlock", "Solar", "wl-b", false, []);
  });

  it("changing character clears a plan computed for the previous one", async () => {
    await renderLoaded();
    applyOutfit.mockResolvedValue({ plan: PLAN, results: [] });

    await userEvent.click(screen.getByRole("button", { name: "Equip" }));
    await screen.findByRole("button", { name: "Equip 1 item" });

    await userEvent.selectOptions(screen.getByLabelText(/Character to equip/), "wl-b");

    expect(screen.queryByRole("button", { name: /^Equip \d+ item/ })).toBeNull();
  });

  it("locks the character picker while a request is in flight", async () => {
    await renderLoaded();
    applyOutfit.mockReturnValue(new Promise(() => {}));

    await userEvent.click(screen.getByRole("button", { name: "Equip" }));

    await waitFor(() =>
      expect((screen.getByLabelText(/Character to equip/) as HTMLSelectElement).disabled)
        .toBe(true));
  });

  it("locks the focus picker while a card is equipping", async () => {
    // Changing focus mid-equip unmounts the card, but the equip still
    // completes server-side with nobody left to report what moved.
    await renderLoaded();
    applyOutfit.mockReturnValue(new Promise(() => {}));

    await userEvent.click(screen.getByRole("button", { name: "Equip" }));

    await waitFor(() =>
      expect((screen.getByRole("button", { name: "Super" }) as HTMLButtonElement).disabled)
        .toBe(true));
  });
});
