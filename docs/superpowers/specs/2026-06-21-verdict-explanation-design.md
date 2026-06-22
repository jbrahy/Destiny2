# Weapon Verdict Explanation + Upgrade Path — Design

**Date:** 2026-06-21
**Status:** Approved (design)

## Context

Each owned weapon gets a verdict badge (God Roll / Upgrade / Good / No Data /
Dismantle) computed in `app/perk_scoring.py::score_weapon`. Today the UI shows
the badge and a terse `note`, but never explains *why* that status was chosen or
*what it would take to reach the next tier*. The user wants both, surfaced in the
weapon detail panel.

The verdict rules are deterministic, so both explanations are derivable from the
same inputs the verdict uses:

- **God Roll** = (an S-tier perk OR ≥2 A/S perks) AND masterworked
- **Upgrade** = same perk quality but NOT masterworked
- **Good** = best perk is A or B
- **No Data** = only C-tier perks (or no rated perks at all)
- **Dismantle** = only D-tier perks, OR a random-roll duplicate when a better
  copy exists

## Goal

For every weapon, show in the detail panel:
1. **Reason** — a short human sentence for why the current status was selected.
2. **Upgrade path** — what reaching the next tier requires (or none, when already
   top tier or a dupe marked for dismantle).

Success criteria:
- The explanation is derived from the same rules as the verdict (cannot drift).
- Covers all five verdicts plus the empty-rated and dupe-demoted special cases.
- Appears only in the weapon detail panel; grid cards are unchanged.
- No new Bungie calls — derived from already-scored data.

## Non-Goals

- No explanation text on the grid cards.
- No changes to the verdict rules themselves.
- No per-stat or per-roll simulation beyond the tier thresholds.

## Architecture

A pure explanation function next to the scoring rules, two new DTO fields, and a
small detail-panel render block.

### Backend (`app/perk_scoring.py`)

New pure function:

```python
def explain_verdict(
    verdict: Verdict,
    rated: list[dict],          # rated perks, already sorted best-first
    is_masterworked: bool,
    is_random_roll: bool,
    dupe_demoted: bool,
) -> tuple[str, str | None]:
    """Return (reason, upgrade_path). reason explains why `verdict` was chosen;
    upgrade_path says what reaching the next tier takes, or None when there is
    no meaningful next step (God Roll, or a dupe marked for dismantle)."""
```

Behavior by verdict (using `TIER_SCORE = {S:5, A:4, B:3, C:2, D:1}`; `strong` =
count of perks rated A/S):

- **GOD_ROLL** — reason: `"Top-tier perks ({names}) and masterworked."`;
  upgrade_path: `None` ("already the best tier").
- **UPGRADE** — reason: `"{strong} A/S-tier perk(s) ({names}) but not masterworked."`;
  upgrade_path: `"Masterwork it → God Roll."`
- **GOOD** — reason: `"Best perk is {tier}-tier ({name}); no S-tier and fewer than two A/S perks."`;
  upgrade_path: `"A second A/S-tier perk (or one S-tier perk) → Upgrade"` +
  `" (re-roll/craft for a better roll)"` when `is_random_roll`.
- **NO_DATA**:
  - if `rated` is empty → reason: `"No perk-rating data for this weapon's perks."`;
    upgrade_path: `"Rate its perks on the Perks tab."`
  - else (only C-tier) → reason: `"Only C-tier perks for this weapon type."`;
    upgrade_path: `"Any A- or B-tier perk → Good"` (+ random-roll suffix as above).
- **DISMANTLE**:
  - if `dupe_demoted` → reason: `"A better-perked copy of this weapon exists in your inventory."`;
    upgrade_path: `None`.
  - else (only D-tier) → reason: `"Only low-value (D-tier) perks."`;
    upgrade_path: `"Any A/B-tier perk → Good"` (+ random-roll suffix as above).

`{names}` lists the A/S perks (or the single best perk where appropriate). The
random-roll suffix is appended only to perk-improvement paths (not the masterwork
path, which applies to any weapon).

### Wiring

`score_by_perks` already computes the final verdict and performs the dupe
demotion. After that pass, for each result it calls `explain_verdict(...)` —
passing `dupe_demoted=True` only for results whose verdict was flipped to
DISMANTLE by the demotion branch — and stores `verdictReason` (str) and
`upgradePath` (str | None) on the result dict. `weapon_to_dict` adds both fields
to its output.

### Frontend

- `WeaponDto` gains `verdictReason: string` and `upgradePath: string | null`.
- `WeaponDetail` renders, beneath the title/meta block: the verdict label, the
  **reason** line, and — only when `upgradePath` is non-null — an
  **"↑ Upgrade path: {upgradePath}"** line. Grid cards (`WeaponCard`) are not
  changed.

## Data Flow

```
score_weapon (verdict + rated)  →  score_by_perks (dupe demotion)
        │                                  │ explain_verdict(final verdict, rated, mw, random, demoted)
        ▼                                  ▼
   weapon_to_dict adds verdictReason + upgradePath
        ▼
   WeaponDto  →  WeaponDetail renders reason + (optional) upgrade-path line
```

## Error Handling

- `upgradePath` is `null` for God Roll and dupe-dismantle; the UI omits the line.
- Empty `rated` (no ratings) is handled explicitly (its own NO_DATA wording).
- `explain_verdict` is total over the five `Verdict` values; an unexpected value
  falls back to `("", None)` so the UI simply shows nothing extra.

## Testing

**Backend (`tests/test_explain_verdict.py`):**
- Each of the five verdicts returns the documented reason shape and correct
  upgrade path.
- UPGRADE → upgrade_path mentions masterwork; GOD_ROLL → upgrade_path is None.
- NO_DATA with empty `rated` vs only-C-tier produce different reasons.
- DISMANTLE dupe-demoted → reason is the dupe message and upgrade_path is None;
  DISMANTLE D-tier → upgrade path present.
- Random-roll vs fixed-roll: the perk-improvement suffix appears only for random
  rolls.
- An integration check that `score_by_perks` populates `verdictReason` /
  `upgradePath` on results, including a dupe-demoted weapon.

**Frontend (`weaponDetail` formatter or component test):**
- The upgrade-path line renders when `upgradePath` is a string and is absent when
  it is `null`.

## Out of Scope / Future

- Surfacing the explanation on grid cards.
- Simulating specific perk swaps or stat changes.
