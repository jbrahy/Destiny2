# Armor Sets & Objective Scoring — Design

**Date:** 2026-07-30
**Status:** Approved design
**Scope:** Set membership/bonuses + an objective armor verdict. Approaches and armor
dismantle are separate specs that build on this.

## Problem

All armor intelligence in this app is ~10 lines of frontend heuristic. There is **no
backend armor module at all** — weapons have seven (`perk_scoring`, `perk_ratings`,
`dismantle`, `chase`, `roll_pool`, `recommend`, `loadout_builder`); armor has zero.

`rate()` in `ArmorList.tsx` scores a piece by **total stats as a percentage of your best
piece in that slot**. Two things are wrong with it:

1. **It is self-referential.** As your gear improves, previously "Top Roll" pieces silently
   demote. Nothing is ever objectively good or bad.
2. **It ignores distribution**, which is the entire signal.

The app also has no concept of armor sets, so it cannot show which set a piece belongs to
or what its bonuses do.

## What the real data says

Measured against the live account (452 pieces, 351 Warlock / 65 Titan / 36 Hunter, 77
exotic, 23 masterworked):

Stats are the reworked six: **Health, Melee, Grenade, Super, Class, Weapons**.

| | Health | Melee | Grenade | Super | Class | Weapons |
|---|---|---|---|---|---|---|
| max | 35 | 35 | 35 | 30 | 40 | 40 |
| min | **-2** | 0 | 0 | 0 | 0 | 0 |

Totals: min 0 · p25 56 · median 71 · p90 88 · max 103.

**Per-stat caps are ~30–40, not 100.** The old "tier every 10 points" model is gone; any
scoring built on tier thresholds would be wrong.

**Pieces are archetype-spiky by design** — two or three stats at 25–35, the rest pinned at
5–6:

```
Sunbracers            Health 25  Melee 30  Weapons 30   rest 6    total 103
Eye of Another World  Class  30  Weapons 25  Melee 20   rest 6    total 103
Wild Anthem Gloves    Super  30  Melee 25  Class  16    rest 6    total 103
```

Three pieces, identical totals, materially different. **Total stats — exactly what `rate()`
uses — is close to meaningless here.**

## Scoring

**`focus` = sum of the top 3 stats.** The piece's usable output, given the rest sit at 5–6
by design. On the samples above: 85, 75, 71 — separating what total conflates.

**`waste` = total − focus.**

Verdict bands are on `focus`, with `total` as tiebreak. Exotics are always a keep: they are
build-defining and cannot be re-rolled.

**`ArmorVerdict`** is a new enum in `app/models.py`, deliberately *separate* from the weapon
`Verdict` — "god roll" and "masterwork" are weapon vocabulary and would be misleading here.
Values reuse the labels already on screen, so nothing users recognise changes name:

| Value | Meaning |
|---|---|
| `exotic` | Exotic — always a keep, never scored on focus |
| `top_roll` | Top-tier focus for its slot |
| `good` | Worth keeping |
| `ok` | Usable, not special |
| `dismantle` | Low focus — the junk band |

Ordering is `exotic > top_roll > good > ok > dismantle`, so the armor dismantle spec can
reuse the weapon blocklist's "block anything above band X" shape.

Ties within the top 3 do not matter — `focus` is a sum, so tie-breaking between equal stats
cannot change it. A piece with fewer than three positive stats simply sums what it has.

**Thresholds are NOT hardcoded and NOT guessed in this spec.** They live in
`backend/app/data/armor_scoring_seed.json`, following the `perk_ratings_seed.json` pattern
(seeded, user-editable, surfaced in-app). Implementation **begins** by computing the `focus`
distribution across the real 452-piece collection and calibrating the bands so they carve an
actual collection sensibly. Anchored on the game's ceiling, not on the user's best piece —
so verdicts do not drift as gear improves.

### Edge cases the data proved real
- `Health` can be **negative** (-2).
- Some pieces total **0**.

Both need explicit tests. Neither may produce a divide-by-zero or a bogus "great roll."

## Set foundation

**Manifest** gains two tables beside the plug sets already downloaded:

| Table | Size | Purpose |
|---|---|---|
| `DestinyEquipableItemSetDefinition` | 25 KB | 56 sets: `setItems[]`, `setPerks[{requiredSetCount, sandboxPerkHash}]` |
| `DestinySandboxPerkDefinition` | 2.4 MB | Resolves bonus names and descriptions |

Cached via `manifest_set` under the same version, so existing invalidation covers them, and
the "re-download when a table is missing" path added for plug sets picks them up without
waiting for a Bungie release.

Verified real: each set has a 2-piece and 4-piece bonus, e.g. *Techsec* 2pc "Wrecker —
significantly increased Kinetic damage to combatant shields, overshields, vehicles and
constructs"; *Last Discipline* 4pc "Power Loader — picking up an Orb of Power grants Special
ammo progress."

**New pure module `backend/app/armor_sets.py`** (stdlib + `app.models` only, mirroring
`dismantle.py` / `roll_pool.py`). Builds an item-hash → set index once per manifest load:

- `set_for(item_hash)` → set name + hash
- `set_bonuses(set_hash)` → `[{count, name, description}, ...]`
- `equipped_set_counts(pieces)` → per-set counts, so the UI can say "3/4 — one more for
  Reactive Booster"

Degrades structurally: no set tables cached → empty index → armor behaves exactly as today.

## Components

| File | Responsibility |
|---|---|
| `backend/app/manifest.py` | *(modify)* download + cache the two new tables; accessors |
| `backend/app/armor_sets.py` | **new, pure** — set index, membership, bonuses |
| `backend/app/armor_scoring.py` | **new, pure** — `focus`/`waste`, verdict bands |
| `backend/app/data/armor_scoring_seed.json` | **new** — editable thresholds |
| `backend/app/models.py` | *(modify)* `ArmorPiece.set_name`, `set_hash` |
| `backend/app/bungie_client.py` | *(modify)* populate set fields in `assemble_armor` |
| `backend/app/main.py` | *(modify)* `_armor_to_dict` gains `verdict`, `focus`, `waste`, set fields |
| `frontend/src/components/ArmorList.tsx` | *(modify)* consume the backend verdict; **delete `rate()`** |
| `backend/app/config.py` | *(modify)* `user_cache_ttl_seconds` 300 → 1800 |

`rate()` is deleted rather than left alongside — one source of truth, backend, tested. The
existing rating **filter** stays; it filters on the backend verdict instead.

### Cache TTL
`user_cache_ttl_seconds` goes 300 → 1800. The 5-minute expiry caused repeated mid-task
failures and is the same root cause that made the "Move to" controls silently vanish from
weapon detail. A Refresh button already exists for when the user has just played.

## Testing

TDD, one file per concern, matching the repo.

- `test_armor_scoring.py` — **write first**: a spread-thin 103 must rank BELOW a focused 95.
  That single assertion is the whole reason this feature exists. Plus: negative `Health`;
  zero-total piece; exotic always a keep; band boundaries exact at each threshold; `focus`
  uses exactly the top 3.
- `test_armor_sets.py` — membership lookup; 2pc/4pc bonuses resolve; unknown item → no set;
  **missing manifest tables → empty index, never a crash**; `equipped_set_counts` across a
  mixed loadout.
- `test_manifest.py` — the two new tables load and degrade when absent.
- Endpoint test — `/api/armor` carries verdict + set fields.

No test may touch a live inventory.

## Verification

1. `cd backend && python -m pytest tests/test_armor_scoring.py tests/test_armor_sets.py
   tests/test_manifest.py -v`. The **full suite is pre-existing broken** (~67 failures from
   cross-file async loop pollution, reproduced with all feature files excluded) — validate
   per-file.
2. `cd frontend && npx tsc --noEmit` (exactly one pre-existing `main.tsx` error) &&
   `npx vitest run`.
3. **Calibration gate:** run the scoring over the real 452-piece collection and inspect the
   verdict distribution before fixing the seed values. If it calls 300 pieces "great," the
   bands are wrong.
4. Spot-check by hand: confirm a known-good spiky piece outranks a known-mediocre high-total
   one, and that set names/bonuses match what the game shows.

## Rollout

1. Set foundation alone — no scoring change, verdicts provably unchanged. Ship.
2. Scoring + seed calibration. **This changes every armor rating in the UI**, deliberately.
3. TTL bump (independent, one line).

Deploys use the known path: build from clean `HEAD`, `COPYFILE_DISABLE=1 tar`, checksum,
preserve `.env`, skip `pip install -e .`, restart, smoke test.

## Out of scope (separate specs)

- **Approaches** — seeded, editable playstyles with stat weights and set affinities, plus the
  dropdown. Needs real scoring output first to be designed sensibly.
- **Best-of-each-set-per-approach keeps.**
- **Armor dismantle** — mostly reuse of `dismantle.py`, the sweep/undo endpoints and
  `user_sweep_items`. Real differences: five armor buckets instead of three (~45 staging
  capacity vs 27) and a blocklist where exotics matter far more. Needs scoring first, or it
  is just a bulk mover that cannot tell good from bad.
