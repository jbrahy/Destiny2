# Weapon Dismantle Sweep — Design

**Date:** 2026-07-28
**Status:** Approved
**Scope:** Weapons only. Armor, consumables, and postmaster items are out of scope.

## Problem

Users want to dismantle weapons from the advisor's web interface.

## Constraint: the Bungie API cannot dismantle

Bungie's Destiny 2 API exposes no endpoint that destroys, deletes, salvages, or
dismantles an item. The complete set under `Destiny2/Actions/Items/` is:

`TransferItem`, `PullFromPostmaster`, `EquipItem`, `EquipItems`, `EquipLoadout`,
`SnapshotLoadout`, `UpdateLoadoutIdentifiers`, `ClearLoadout`, `SetItemLockState`,
`SetQuestTrackedState`, `InsertSocketPlug`, `InsertSocketPlugFree`.

This omission is deliberate on Bungie's part. Destiny Item Manager, the reference
third-party inventory tool, documents the same limitation: it cannot dismantle
items either.

Literal one-click dismantle is therefore not buildable. This design delivers the
achievable substitute.

## Solution: stage in the app, sweep in-game

The app stages a dismantle batch — unlocking the chosen weapons and moving them
onto a single character — so the user dismantles them from one in-game inventory
screen instead of hunting item by item.

Every action the app takes is reversible. The only irreversible step is the user
holding the dismantle button in-game.

## Selection

Two sources, visually distinguished in the UI:

1. **Junk-tagged weapons** — from the existing `user_item_tags` table
   (`keep | junk | infuse | favorite`). Pre-checked.
2. **Low-verdict suggestions** — C/D-tier rolls from `perk_scoring`. Start
   **unchecked**; the user opts each one in.

The app never selects a weapon for destruction without an explicit user action.

B-tier rolls sit between the two: not suggested, not blocked. They enter a sweep
only if the user tagged them junk.

## Blocklist (server-enforced)

Enforced in the backend. The client is never trusted with these rules.

| Rule | Behavior |
|---|---|
| Exotic (`tier_type == 6`) | Blocked; explicit per-instance override required |
| Verdict `S` or `A` from `perk_scoring` | Blocked; explicit per-instance override required |
| Currently equipped on any character | Hard block; no override (the game rejects it regardless) |

Overrides are per-instance and echo back into the confirmation list, so an
overridden exotic is still visibly an exotic at the moment of commit.

## Batching

A character's weapon buckets (kinetic, energy, power) hold 10 items each including
the equipped one — 9 stageable per bucket, minus current occupancy. Batching is
imposed by the game, not a design choice.

The batch planner fills to 9 unequipped per bucket and defers the remainder. The
UI reports the split explicitly ("31 selected, 12 fit on Titan this batch") with
the per-bucket breakdown, so the limit is visible rather than mysterious.

## Backend

**New module `app/dismantle.py`** — blocklist evaluation and batch planning as
pure functions. HTTP handlers in `main.py` stay thin, matching the existing
`perk_scoring.py` / `loadout_builder.py` split.

**New client call in `bungie_client.py`** — `set_item_lock_state()` →
`POST /Destiny2/Actions/Items/SetItemLockState/`, alongside `transfer_item`.

**Endpoints:**

| Endpoint | Purpose |
|---|---|
| `POST /api/dismantle/preview` | Returns candidates (tagged vs suggested), `blocked[]` with reasons, and the batch plan |
| `POST /api/dismantle/sweep` | Per item: unlock, then transfer to character. Sequential, through `bungie_throttle.py` |
| `POST /api/dismantle/undo` | Transfer back to vault and restore prior lock state |

**Ordering guarantee:** unlock strictly precedes transfer for each item.

**New table** — undo cannot restore a lock state that was never recorded:

```
user_sweep_items (user_id, instance_id, was_locked, staged_at)
```

Follows the `user_item_tags` pattern in `repositories/user_tables.py`.

## Frontend

Nav is a `Section` union with state-based switching, not a router. Integration is:
add `"dismantle"` to `Section` and `SECTIONS` in `Nav.tsx`, plus a branch in
`AppShell.tsx`.

**New `DismantlePage.tsx`:**

- **Preview state** — candidate table: icon, name, perks, verdict, power, and a
  *why* column distinguishing "you tagged this junk" from "suggested: D-tier roll".
  Blocked rows render greyed with a red reason chip and an `Override` toggle that
  turns them red-but-included.
- **Batch banner** — selected count, count that fits this batch, per-bucket breakdown.
- **Staged state** — "12 weapons moved to Titan. Dismantle them in-game, then run
  batch 2." Plus `Undo sweep`.

Reuses `TagChip` from `TagSelect.tsx` and verdict styling from `WeaponCard.tsx`.

## Error handling

Sweeps make partial progress by nature. The sweep endpoint returns per-item status,
leaves successfully-staged items staged, and lists failures inline.

No automatic rollback. Undo stays user-driven: a half-rolled-back sweep leaves the
inventory in a less comprehensible state than a clearly-reported partial one.

Bungie error codes map to readable messages via the existing `_raise_for_bungie`
path. Token expiry uses the existing auth refresh path.

## Testing

TDD, matching the existing one-file-per-concern layout under `backend/tests/`.

| File | Covers |
|---|---|
| `test_dismantle_blocklist.py` | Exotics and S/A verdicts blocked; override permits; equipped never permitted even with override |
| `test_dismantle_batching.py` | Capacity math against pre-occupied buckets; remainder ordering |
| `test_dismantle_undo.py` | `was_locked` recorded on stage, restored on undo |
| `test_endpoints_dismantle.py` | Endpoint wiring, following `test_endpoints_transfer.py` |

All tests run against a fake Bungie client asserting call order (unlock strictly
before transfer). No test touches live inventory.

`test_dismantle_blocklist.py` is the highest-value file: it is the guard against
destroying something irreplaceable.

## Out of scope

- Armor, consumables, postmaster items
- Scheduled or automatic sweeps — every sweep is user-initiated
- Any attempt to simulate dismantle server-side

## References

- [Bungie.net API endpoint index](https://bungie-net.github.io/multi/index.html)
- [DIM Troubleshooting — "DIM will not be able to dismantle any of your items"](https://github.com/DestinyItemManager/DIM/wiki/Troubleshooting)
