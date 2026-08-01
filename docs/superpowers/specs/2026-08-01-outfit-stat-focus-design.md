# Outfit Stat Focus — Design

**Date:** 2026-08-01
**Status:** Approved design
**Scope:** A stat picker on the Outfits page that drives armor selection for every outfit.

## Problem

Outfits currently rank armor by each build's seeded `statPriority` — a guess inferred from the
build's own prose. There is no way to say "I want Grenade and Super right now" and see what that
actually gets you.

## What it does

One picker at the top of the Outfits page offering the six armor stats: `Health, Melee, Grenade,
Super, Class, Weapons`. Choose **1–3**. Every outfit re-picks its armor to maximise the chosen
stats.

**Choosing nothing keeps today's behaviour**: each outfit falls back to its own seeded
`statPriority`, so the page opens unchanged and only diverges once you pick.

## The consequence, stated plainly

A single global focus that replaces the seeded priorities means **all six subclasses of a class get
identical armor**. Armor selection then depends on class + chosen stats only; subclass stops being
an input.

This is correct, not a regression. Armor is class-locked, not subclass-locked — if you asked for
Grenade + Super, the best Grenade/Super Warlock helmet is the best one whichever subclass you run.
The 18 outfits still differ by weapons, which key off the subclass damage element. The armor block
will visibly repeat across a class's six cards, and that repetition is the truth.

## Where the focus is applied

`priority = focus or build.get("statPriority", [])` inside `build_outfit`. Everything downstream —
`_armor_score`, the exotic solver, the returned `statPriority` field — is unchanged.

The outfit's returned `statPriority` reports **what was actually used**, so the card's
"prioritising …" subtitle stays honest under either mode.

## Both endpoints take the focus

`GET /api/outfits?focus=Grenade,Super` **and** `POST /api/outfits/apply {…, focus: [...]}`.

This is not symmetry for its own sake. `/api/outfits/apply` rebuilds the outfit server-side rather
than trusting the client's item list. If it rebuilt without the focus, you would review and equip
an outfit assembled from the *seeded* priority while looking at one assembled from your focus — the
preview and the page would disagree about which items the outfit even contains. The focus is part
of the outfit's identity and must travel with every request that reconstructs it.

## Validation

Shared by both endpoints, so they cannot drift:

- Each name must be one of the six armor stats → else 400 naming the offender.
- At most 3 → else 400.
- Duplicates collapse; order is not significant.
- Empty/absent → seeded fallback, not an error.

## Components

| File | Responsibility |
|---|---|
| `backend/app/outfits.py` | *(modify)* `ARMOR_STATS`; `focus` parameter through `build_outfit` / `build_all_outfits`; `parse_focus` (pure validation) |
| `backend/app/main.py` | *(modify)* `focus` query param on `GET /api/outfits`; `focus` field on `ApplyOutfitBody`; both routed through `parse_focus` |
| `frontend/src/api.ts` | *(modify)* `fetchOutfits(focus)`, `applyOutfit(..., focus)` |
| `frontend/src/components/OutfitsPage.tsx` | *(modify)* the picker; refetch on change; pass focus to equip |

## Interface

```python
ARMOR_STATS = ("Health", "Melee", "Grenade", "Super", "Class", "Weapons")

def parse_focus(raw: str | list[str] | None) -> list[str]:
    """Validated 0-3 armour stats. Raises ValueError with the offending name."""

def build_outfit(class_name, subclass, weapons, armor, build, focus=None) -> dict:
def build_all_outfits(builds, weapons, armor, focus=None) -> list[dict]:
```

`parse_focus` raising `ValueError` keeps `outfits.py` free of FastAPI; `main.py` translates it to a
400.

## UI

Six toggle buttons in a row above the outfit grid, each on/off. A selected stat is filled with
`var(--accent)`. Selecting a fourth is refused with a short inline note rather than silently
dropping one. A "Clear" control returns to the seeded default, labelled so it is obvious that
clearing is not "no priority" but "use each build's own".

Changing the picker refetches. Any open confirm panel is discarded on change — a plan computed for
one focus must never be confirmed against another, the same rule the character picker already
follows.

## Testing

- `test_outfits.py` (pure): `parse_focus` accepts 1–3 valid stats, collapses duplicates, rejects an
  unknown name (naming it) and rejects 4; empty → `[]`. `build_outfit` with a focus overrides the
  seeded priority and reports the focus in `statPriority`; without one, falls back to the seed.
  A test that a focus actually changes which piece is chosen, not merely the reported field.
- `test_endpoints_outfits.py`: `?focus=` round-trips; `?focus=Nonsense` → 400; four stats → 400;
  and **apply with a focus rebuilds with that focus** — the plan must name the focused pick, not
  the seeded one.

## Out of scope

- Per-outfit focus overrides (a page-level picker only).
- Focus affecting weapon selection — weapons key off the subclass damage element and are unchanged.
- Persisting the chosen focus across sessions.
