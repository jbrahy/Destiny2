# Save Armor Sets — Design

**Date:** 2026-06-21
**Status:** Approved (design)

## Context

The Armor Optimizer (`frontend/src/components/ArmorPage.tsx`) computes the best
5-piece armor set for a chosen class and stat priorities, entirely client-side.
Today the result is display-only — the user cannot persist a set they like. This
feature lets the user **save an optimized armor set** under a name and target
character, view their saved sets, and **apply** (equip) one later.

The existing weapon-loadouts system already persists `{name, characterId,
items:[{instanceId,itemHash}]}` and equips them via `POST /api/loadouts/apply`.
Armor pieces are instanced items (`instanceId` + `itemHash`), so the *apply*
mechanism is identical. Per the user's decision, armor sets live in a **separate
store** (not mixed into weapon loadouts).

## Goal

- Save the optimizer's current 5-piece set as a named Armor Set with a target
  character.
- List saved Armor Sets on the Armor page.
- Apply a saved set (move + equip its pieces to its stored character).
- Delete a saved set.

Success criteria:
- A saved set round-trips: save → appears in the list → apply equips the pieces
  → delete removes it.
- Armor Sets are stored separately from weapon loadouts.
- The Bungie move/equip loop is **not duplicated** — loadout-apply and
  armor-set-apply share one helper.

## Non-Goals

- No mixing with the weapon-loadouts store or the Loadouts tab UI.
- No new nav tab — the saved-sets list lives on the existing Armor page.
- No armor mods / fragment-bonus modeling (the optimizer already states it uses
  base stats only).
- No save-and-equip-in-one-click (save and apply are distinct actions).
- No multi-character or cross-class sets — a set is class-scoped with one target
  character.

## Architecture

A dedicated store mirroring the loadouts pattern, plus a shared apply helper.

### Backend (`app/main.py`)

**Table:** `armor_sets(name TEXT PRIMARY KEY, data TEXT)`, created by an
`_ensure_armor_sets(conn)` helper (mirrors `_ensure_loadouts`). `data` JSON:

```json
{
  "className": "Warlock",
  "characterId": "2305...",
  "tier": 17,
  "items": [
    {"instanceId": "69...", "itemHash": 123, "slot": "Helmet", "name": "Ferropotent Cover"}
  ]
}
```

Storing `slot` + `name` lets the saved set render without re-fetching the vault.

**Model:**

```python
class ArmorSetBody(BaseModel):
    name: str
    className: str
    characterId: str
    tier: int
    items: list[dict]  # [{instanceId, itemHash, slot, name}]
```

**Endpoints:**
- `GET /api/armor-sets` → `{"armorSets": [{name, ...data}]}`
- `PUT /api/armor-sets` (upsert by name) → `{"ok": true}`
- `DELETE /api/armor-sets/{name}` → `{"ok": true}`
- `POST /api/armor-sets/apply` (body `{name}`) → equip stored items to the stored
  `characterId`; returns `{"results": [{instanceId, ok, error?}]}`. 404 if the
  set is unknown.

**Refactor (targeted, DRY):** the move/equip loop inside `apply_loadout`
(open httpx client → `_valid_access_token` → loop `_move_one(..., equip=True)`
→ refresh + `_save_profile`) is extracted into:

```python
async def _apply_item_set(conn, settings, items: list[dict], target: str) -> list[dict]:
    """Move+equip each {instanceId,itemHash} item to the target character.
    Returns per-item results. Shared by loadout-apply and armor-set-apply."""
```

`apply_loadout` is rewritten to call it; `armor-sets/apply` calls the same
helper. Behavior of loadout-apply is unchanged (existing tests must stay green).

### Frontend

**Types (`types.ts`):**

```typescript
export interface ArmorSetItem { instanceId: string; itemHash: number; slot: string; name: string; }
export interface ArmorSet {
  name: string; className: string; characterId: string; tier: number; items: ArmorSetItem[];
}
```

**API (`api.ts`):** `fetchArmorSets()`, `saveArmorSet(set)`, `deleteArmorSet(name)`,
`applyArmorSet(name)` — following existing fetch/`res.ok`/throw patterns.

**Pure helper (`armorSet.ts`):**

```typescript
// Build the persisted items array from the optimizer's chosen map, skipping empty slots.
armorSetItems(chosen: Record<string, ArmorPiece | null>): ArmorSetItem[]
// Overall tier = floor(sum of all stat values across chosen pieces / 10).
armorSetTier(chosen: Record<string, ArmorPiece | null>): number
```

`armorSetItems` preserves the canonical slot order (Helmet, Gauntlets, Chest
Armor, Leg Armor, Class Item) and maps each piece to
`{instanceId, itemHash, slot, name}`.

**ArmorPage additions:**
- A **"Save this set"** row beneath the optimizer table: a name `<input>`, a
  character `<select>` filtered to characters whose `className` equals the
  selected class, and a **Save** button. On save: `saveArmorSet({name, className:
  cls, characterId, tier: armorSetTier(chosen), items: armorSetItems(chosen)})`,
  then refresh the list. Save is disabled unless name is non-empty, a target
  character is selected, and `armorSetItems(chosen).length > 0`.
- A **"Saved armor sets"** section listing each set: `name · class · Tier N · K
  pieces`, with **Apply** (window.confirm → `applyArmorSet` → report per-item
  failures, with the "Re-login if permission error" caveat) and **Delete**
  (confirm → `deleteArmorSet`). Sets are fetched on mount and after any
  save/delete.

## Data Flow

```
ArmorPage optimizer → chosen: Record<slot, ArmorPiece|null>
   │ armorSetItems + armorSetTier (pure)
   ▼
PUT /api/armor-sets  → armor_sets table
   ▲                         │
GET /api/armor-sets ◀────────┘
   │ user clicks Apply
   ▼
POST /api/armor-sets/apply → _apply_item_set(conn, settings, items, characterId)
                              → _move_one(..., equip=True) per item  (shared w/ loadout-apply)
```

## Error Handling

- `PUT` with missing fields → 422 (Pydantic).
- `apply` on unknown set name → 404.
- Apply move failures (e.g. missing write scope) → reported per item in
  `results`; UI surfaces a "Re-login" hint, matching the weapon-loadout UX.
- Empty/partial optimizer result (a slot has no owned armor) → those slots are
  skipped in `items`; save still allowed if ≥1 piece, but Save is disabled when 0.

## Testing

**Backend (`tests/test_armor_sets.py` + endpoint tests):**
- CRUD round-trip: `PUT` then `GET` returns the set with all fields; `DELETE`
  removes it.
- `PUT` missing required field → 422.
- `apply` unknown set → 404.
- Existing `test_api.py` loadout-related tests stay green after the
  `_apply_item_set` extraction (regression guard for the refactor).

**Frontend (`armorSet.test.ts`):**
- `armorSetItems` maps fields and skips null slots, in canonical slot order.
- `armorSetTier` = floor(total-of-all-stats / 10), and 0 for an empty/all-null
  set.

## Out of Scope / Future

- Editing a saved set's individual pieces.
- Showing saved-set stat breakdowns (only tier + piece count in v1).
- Armor mods / masterwork energy in the tier calc.
