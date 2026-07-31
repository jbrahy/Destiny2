# Outfits — Design

**Date:** 2026-07-31
**Status:** Approved design
**Scope:** One button producing a complete, equippable outfit for every class/subclass
combination, read-only.

## Problem

`build_loadout` picks the top weapon per ammo slot for an *activity*. It has **no armor
awareness at all** — `recommend.py` contains zero armor references — and it does not work per
class/subclass. There is no way to answer "what should I actually wear as a Solar Warlock?"

The pieces to answer it now exist: 18 seeded class|subclass builds, weapon verdicts and
`matchedPerks`, and (as of today) objective armor scoring plus set bonuses.

## What it does

A button generates **18 outfits** — Hunter/Titan/Warlock × Arc/Solar/Void/Stasis/Strand/Prismatic,
exactly the keys already in `builds_seed.json`. Each outfit is 5 armor pieces + 3 weapons, with
each pick showing *why*: weapons list their `matchedPerks`, armor shows its set name, 2pc/4pc
bonuses and `focus`.

**Read-only.** No Bungie writes, no mod insertion, no perk changes. Perks are *displayed*, not
selected or applied.

## The two rules that make this non-trivial

Destiny allows exactly **one exotic armor piece** and **one exotic weapon** equipped at a time.
Greedy per-slot selection ignores this: if the best Helmet and the best Gauntlets are both exotic,
the result is an outfit the player **cannot equip**.

With 5 armor slots and 3 weapon slots the search is tiny, so solve it exactly rather than
approximate: for each slot pick the best legendary *and* the best exotic, then choose which single
slot (if any) spends the exotic allowance on whichever swap gains the most. Same shape for weapons.

This is the correctness heart of the feature and gets tested first.

## Armor selection — stat priority

Objective `focus` alone is subclass-blind, so the top-focus Warlock armor would be identical for
all six Warlock subclasses — 18 outfits containing 3 distinct armor sets.

Each seeded build therefore gains **`statPriority`**: 2–3 of `Health, Melee, Grenade, Super, Class,
Weapons`. Armor is then scored per-slot on the sum of the priority stats, tie-broken on `focus`.

Priorities are **seeded from the prose already in each build** (`Titan|Solar` says "Throwing Hammer
loop" → Melee) and are user-editable, carrying the same caveat as the build seeds themselves: they
are a starting point derived from dated knowledge, not authority.

Armor is **class-locked** — Warlock armor only appears in Warlock outfits.

## Weapon selection

Reuse `recommend_weapons` with the subclass element, which already ranks by verdict with
element-synergy bonuses and already varies per subclass. Take one per ammo slot, subject to the
one-exotic rule.

## Components

| File | Responsibility |
|---|---|
| `backend/app/outfits.py` | **new, pure** — slot picking, exotic constraint, outfit assembly |
| `backend/app/data/builds_seed.json` | *(modify)* add `statPriority` to all 18 builds |
| `backend/app/main.py` | *(modify)* `GET /api/outfits` |
| `frontend/src/api.ts` | *(modify)* `fetchOutfits()` + types |
| `frontend/src/components/OutfitsPage.tsx` | **new** — the 18 outfits |
| `frontend/src/components/Nav.tsx`, `AppShell.tsx` | *(modify)* new section |

Reused, not rebuilt: `recommend_weapons`, `armor_scoring.focus`, `armor_set_bonuses.set_bonuses`,
`builds_seed.json`, `assemble_armor`.

## Known limits, stated up front

- **Hunter and Titan outfits will be thin.** The live collection is 351 Warlock / 65 Titan / 36
  Hunter pieces — roughly 7 Hunter pieces per slot, so those 12 outfits are near-forced picks.
- A slot with no owned armor yields `null` rather than a fabricated pick.
- `statPriority` is inferred from prose and will need correcting.

## Testing

TDD, one file per concern.

- `test_outfits.py` — **write the exotic-constraint tests first**:
  - two exotic-best slots → exactly one exotic in the result, and it is the higher-gain swap
  - all-legendary input → unchanged by the constraint
  - one exotic weapon max, independently of armor
  - a slot with no armor for that class → `null`, not a crash
  - stat priority actually changes the pick vs pure focus
  - class-locking: Warlock outfits never contain Titan armor
  - all 18 combos produced, keyed off `builds_seed.json`
- Endpoint test: `/api/outfits` shape, 401 unauthenticated, 400 without cached inventory.

No test touches a live inventory.

## Verification

1. Per-file backend runs (full suite is pre-existing broken — ~67 cross-file async failures).
2. `npx tsc --noEmit` (one pre-existing `main.tsx` error) && `npx vitest run`.
3. Manual: open Outfits, confirm each outfit has ≤1 exotic armor and ≤1 exotic weapon, that
   Warlock outfits contain only Warlock armor, and that two subclasses of the same class differ.

## Out of scope

- Applying an outfit (the existing loadout save/apply already covers equipping).
- Setting armor mods or weapon perks — read-only was the explicit choice.
- Set-bonus-driven selection.
