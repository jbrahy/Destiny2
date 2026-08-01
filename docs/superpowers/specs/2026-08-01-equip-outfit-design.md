# Equip an Outfit — Design

**Date:** 2026-08-01
**Status:** Approved design
**Scope:** An Equip button on each outfit card that transfers and equips all 8 items to a chosen
character of that class.

## Problem

Outfits shipped read-only: the page tells you what to wear and gives you no way to wear it. The
gear is scattered across the vault and three characters, so acting on an outfit by hand means
eight manual transfers in-game.

## What it does

Each outfit card gains a character picker (every character of that outfit's class, with light
level) and an **Equip** button. Pressing Equip opens a confirm listing what will happen to each of
the eight items; confirming runs it and reports per-item results.

## The two-call endpoint

`POST /api/outfits/apply` takes `{className, subclass, characterId, dryRun}`.

- `dryRun: true` makes **no Bungie call at all**. It classifies each item against the cached
  profile and returns the plan. This fills the confirm dialog.
- `dryRun: false` runs that same plan through the existing `_apply_item_set`.

One endpoint rather than two means the preview and the real run cannot drift into two different
pieces of logic that disagree.

## The outfit is rebuilt server-side

The client sends only `className` + `subclass`. The server re-runs `build_all_outfits` (~10 ms,
measured) and selects the match. The client never supplies instance IDs.

This is a security boundary, not an optimization: an endpoint that equips a caller-supplied list of
instance IDs is a general-purpose "equip anything" primitive, which is a much larger thing to get
right than "equip the outfit you already computed."

## The classifier

`plan_apply(outfit, target, locate) -> list[dict]` is a new **pure** function in `app/outfits.py`.
It mirrors `_move_one`'s rules exactly, so the preview cannot promise something the run will refuse:

| Location (`locate(instanceId)`) | Action | Shown as |
|---|---|---|
| `equipped:<target>` | `skip` | already equipped |
| `equipped:<other char>` | `blocked` | equipped on another character |
| `vault` or another character id | `move` | will be transferred and equipped |
| `None` | `blocked` | not in your cached inventory — refresh |

`locate` is injected (in production, `_find_item_location(profile, ...)` from `main.py`), which
keeps the function free of profile-shape knowledge and trivially testable.

**The blocked row is why the confirm exists.** With 351 Warlock pieces across three characters, the
best piece for a slot is often already worn by your *other* character of the same class, and
Destiny will not let an item be stripped off a character remotely. Learning that before pressing is
the difference between a useful button and a red wall of errors.

## Guard rails

- **CSRF-protected.** It is a write.
- **The target character must exist in the caller's own profile**, and its `className` must match
  the outfit's class. Fail fast with 400 rather than letting Bungie reject eight items one at a
  time.
- Unknown `className|subclass` → 404.
- No cached inventory → 400, same as the sibling endpoints.

## Character selection

The picker always renders, even when you own only one character of that class. Consistency beats
saving a click here: the button's target is the single most consequential thing about it, and a
control that appears only sometimes is a control you stop reading.

## One fix folded in

`_apply_item_set` catches `BungieApiError` and `httpx.HTTPStatusError` but **not**
`httpx.RequestError` — a sibling class, not a subclass. A network blip mid-apply escapes the
per-item handler as a 500, discarding the results for every item after it. This is the same bug
class that bit the dismantle sweep. This feature makes that function far more heavily used, so the
net gets widened as part of the work.

## Components

| File | Responsibility |
|---|---|
| `backend/app/outfits.py` | *(modify)* `plan_apply` — pure classification |
| `backend/app/main.py` | *(modify)* `POST /api/outfits/apply`; widen `_apply_item_set` exceptions |
| `frontend/src/api.ts` | *(modify)* `applyOutfit()` + types |
| `frontend/src/components/OutfitsPage.tsx` | *(modify)* character picker, confirm, results |

Reused, not rebuilt: `_apply_item_set`, `_move_one`, `_find_item_location`, `build_all_outfits`,
`/api/characters`.

## Known limits, stated up front

- **A full bucket fails that item.** A character holds 9 items per bucket; if yours is full the
  transfer fails and is reported per-item. Automatically clearing space by moving your gear
  elsewhere is a much larger and riskier feature, deliberately not attempted.
- **Gear only — the subclass is not switched.** A "Warlock | Solar" outfit equips gear chosen for
  a Solar build but leaves you on whatever subclass you are currently running.
- **Partial success is normal**, not an error state. The results panel treats it as such.
- The preview reflects the cached profile; if the game state changed since the last inventory load,
  the run is the authority and the results panel says so.

## Testing

TDD.

- `test_outfits.py` — `plan_apply`, pure, one test per row of the table above, plus: an outfit with
  `None` slots produces no entries for them, and the returned order matches the outfit's slot order.
- `test_endpoints_outfits.py` — 401 unauthenticated; 403 without CSRF; 404 on unknown
  `className|subclass`; 400 when `characterId` is not in the profile; 400 when the character's class
  does not match the outfit's; and **`dryRun: true` issues zero Bungie calls** (asserted, not
  assumed).

No test touches a live inventory.

## Verification

1. Per-file backend runs (the full suite is pre-existing broken — ~67 cross-file async failures).
2. `npx tsc --noEmit` (one pre-existing `main.tsx` error) && `npx vitest run`.
3. Manual, and this is the one that matters: pick an outfit, confirm the preview names the right
   character and correctly flags anything worn elsewhere, equip it, and verify in-game.

## Out of scope

- Switching subclasses, aspects, fragments, or mods.
- Making room in a full bucket.
- Undo. The existing loadout save/apply already lets you snapshot and restore a loadout.
