# Best-from-Vault Weapon Recommendations — Design

**Date:** 2026-06-21
**Status:** Approved (design)
**Sub-feature 1 of 3** in the Recommendations Hub decomposition.

## Context

The Destiny 2 Weapon Advisor already scores every owned weapon by its rolled
perks against the perk-ratings engine, producing a verdict
(`GOD_ROLL` / `UPGRADE` / `GOOD` / `NO_DATA` / `DISMANTLE`), rated perks, tags,
masterwork flag, and a duplicate flag. This data is cached in `weapons_cache`.

Separately, the app stores curated **activities** (with a `recommendedSubclass`)
and **subclass builds**, today mostly free-text guidance.

The Recommendations Hub was decomposed into three independently-shippable
sub-features:

1. **Best-from-vault per slot** (this spec) — the foundation ranking engine.
2. **Activity loadout builder** — composes #1 with subclass builds + cross-weapon
   constraints. (Future spec.)
3. **Weapons to chase** — diffs a curated meta dataset against the vault.
   (Future spec.)

This spec covers **#1 only**.

## Goal

For a chosen **context**, rank the weapons the user already owns, grouped by
ammo slot, so the user can quickly see their best options per slot.

Success criteria:
- Given cached scored weapons + a context, the engine returns weapons grouped
  into Primary / Special / Heavy, each ranked best-first.
- DISMANTLE-tier weapons are excluded.
- Activity contexts apply an element-synergy bonus; general contexts do not.
- A new "Recommend" tab lets the user pick a context and see the ranked results.
- Reuses the existing scored-weapon cache — **no new Bungie API calls**.

## Non-Goals

- No new Bungie API calls or data fetches (consume existing `weapons_cache`).
- No cross-weapon constraints (element coverage, anti-champion, DPS/add-clear
  role balance) — that is sub-feature #2.
- No recommendations for weapons the user does not own — that is sub-feature #3.
- No PvP-specific quality model (see PvE/PvP decision below).

## Architecture

A new pure module plus one read-only endpoint and one frontend tab.

### Backend: `app/recommend.py`

A pure function over already-computed data:

```
recommend_weapons(weapons: list[dict], context: Context, top_n: int = 5) -> dict
```

- `weapons` is the list of scored weapon dicts (the same shape produced by
  `weapon_to_dict`, as stored in `weapons_cache["weapons"]`).
- `context` carries: kind (`general-pve` | `general-pvp` | `activity`) and, for
  activities, the resolved element from `recommendedSubclass`.
- Returns:

```json
{
  "context": "<label>",
  "slots": {
    "Primary": [<ranked weapon dict + recommendReason>, ...],
    "Special": [...],
    "Heavy":   [...]
  }
}
```

The function is the single unit of business logic and is fully unit-testable
without a DB, network, or manifest.

#### Ranking

Each weapon gets a sortable key, best-first:

1. **Verdict tier** (primary): `GOD_ROLL`=5, `UPGRADE`=4, `GOOD`=3, `NO_DATA`=1,
   `DISMANTLE`=0. `DISMANTLE` weapons are dropped before ranking.
2. **Element-synergy bonus** (activity contexts only): +1 to the effective tier
   when the weapon's element matches the activity's subclass element. General
   contexts and Prismatic/Any activities apply no bonus.
3. **Strong-perk count** (tiebreaker): number of A/S-rated perks
   (`matchedPerks` length).
4. **Masterwork** (tiebreaker): masterworked weapons rank above non-MW.
5. **Power** (tiebreaker): higher power first.

Ties remaining after all keys fall back to weapon name (stable, deterministic).

#### Slot grouping

By `ammoType`: `Primary`, `Special`, `Heavy`. Weapons with an empty/unknown
ammo type are omitted from the grouped output (they cannot be slotted).

#### `recommendReason`

A short human string per recommended weapon, e.g.:
- `"S-tier roll"` (verdict-driven), and/or
- `"element-matched for Solar"` (when the activity element bonus applied).

Joined with `" • "` when both apply.

#### Element mapping

`recommendedSubclass` → element: `Solar`, `Arc`, `Void`, `Stasis`, `Strand`
map to themselves; `Prismatic` and `Any` map to "no bonus".

### Backend: endpoint

`GET /api/recommendations?context=<value>`

- `context` is `general-pve`, `general-pvp`, or an exact activity `name`.
- Loads `weapons_cache`; if absent, recomputes from cache the same way
  `/api/weapons` does (`_recompute_from_cache`). If still unavailable, returns
  an empty `slots` payload (consistent with the not-logged-in / no-data state).
- For an activity context, resolves the activity from `load_activities` to get
  its `recommendedSubclass` → element. Unknown activity name → treated as a
  general (no-bonus) context.
- Returns the `recommend_weapons` result.

### PvE vs PvP decision

The only quality signal is the perk-ratings engine, which is PvE-oriented.
For v1, **General PvP uses the same quality ranking as General PvE** with the
element bonus off. The UI shows a visible note that PvP-specific ratings are
future work. This avoids inventing data we do not have.

### Frontend: "Recommend" tab

- New top-nav tab "Recommend".
- A context dropdown populated from: `General (PvE)`, `General (PvP)`, then each
  activity name from `/api/activities`.
- On selection, calls `/api/recommendations?context=...` and renders three
  sections — Primary / Special / Heavy — each a ranked list of cards reusing the
  existing weapon card component, annotated with `recommendReason`.
- When General (PvP) is selected, show the PvP-ratings caveat note.
- Empty state when a slot has no qualifying weapons.

## Data Flow

```
weapons_cache (existing)
        │  list[scored weapon dict]
        ▼
GET /api/recommendations?context=X
        │  resolve context (activity → element)
        ▼
recommend_weapons(weapons, context)   ← pure, unit-tested
        │  grouped + ranked + reasons
        ▼
Recommend tab (context dropdown + 3 slot sections)
```

## Error Handling

- No `weapons_cache` and nothing to recompute → return empty `slots`
  (`{Primary: [], Special: [], Heavy: []}`); frontend shows "log in / refresh
  your vault" style empty state.
- Unknown `context` value → treat as general (no element bonus), do not error.
- Weapons missing `ammoType` → omitted from output, not an error.

## Testing

**Backend (`recommend_weapons`, pure unit tests):**
- Groups weapons into Primary / Special / Heavy by `ammoType`.
- Orders by verdict tier within a slot.
- Activity element match boosts a matching weapon above a higher-base
  non-matching weapon at the boundary; general context does not.
- DISMANTLE-tier weapons are excluded.
- Masterwork and power tiebreakers apply in the documented order.
- Empty input → empty slots.
- `top_n` truncation works.

**Endpoint:**
- Returns grouped payload from a seeded cache.
- Empty cache → empty slots, 200.

**Frontend (Vitest):**
- Context dropdown options are built from general modes + activities list.

## Out of Scope / Future

- Sub-feature #2 (loadout builder) and #3 (weapons to chase).
- PvP-specific perk ratings.
- Anti-champion / element-coverage cross-weapon logic.
