# "Masterwork → God Roll" Verdict — Design

**Date:** 2026-06-21
**Status:** Approved (design)

## Context

Weapon verdicts are computed in `app/perk_scoring.py::score_weapon`. The current
`UPGRADE` verdict is assigned **only** when a weapon has god-roll-quality perks
(an S-tier perk, or ≥2 A/S perks) but is **not masterworked**:

```python
verdict = Verdict.GOD_ROLL if weapon.is_masterworked else Verdict.UPGRADE
```

So `UPGRADE` already means exactly "this becomes a God Roll the moment you
masterwork it." The user wants that status to say so. Per the user's decision we
**replace the `upgrade` value with a new `masterwork` value** labeled
**"Masterwork → God Roll"** (rather than relabel-only, and rather than leave a
dead `upgrade` value).

## Goal

- A distinct verdict value `masterwork` (display label "Masterwork → God Roll")
  is emitted for the not-masterworked-god-roll case, replacing `upgrade`.
- All verdict labels render from one canonical map, fixing a pre-existing
  inconsistency (detail/compare showed raw `"upgrade"`; cards showed `"Upgrade"`).

Success criteria:
- `score_weapon` emits `Verdict.MASTERWORK` (value `"masterwork"`) for the
  god-roll-perks-but-not-masterworked case; `upgrade` no longer exists anywhere.
- Cards, detail panel, compare panel, the Builds page, and the Filters dropdown
  all show "Masterwork → God Roll" for this verdict.
- Recommendation ranking is unchanged (the new value keeps tier 4).
- Backend + frontend test suites pass.

## Non-Goals

- No change to the *trigger* logic (still S-perk or ≥2 A/S perks, not masterworked).
- No change to the other four verdicts' triggers, colors, or labels.
- No change to recommendation tier weights or ordering.
- No change to `explain_verdict`'s reason/upgrade-path text (it already reads
  "…but not masterworked." / "Masterwork it → God Roll.").

## Architecture

A pure value rename across the backend enum + a single canonical label map on the
frontend used by every consumer.

### Backend

- `app/models.py`: replace `UPGRADE = "upgrade"` with `MASTERWORK = "masterwork"`
  in `class Verdict`.
- `app/perk_scoring.py`:
  - `score_weapon`: `verdict = Verdict.GOD_ROLL if weapon.is_masterworked else Verdict.MASTERWORK`.
  - `score_by_perks`: the `keepers` set becomes `{GOD_ROLL, MASTERWORK, GOOD}`.
  - `explain_verdict`: the `verdict == Verdict.UPGRADE` branch becomes
    `verdict == Verdict.MASTERWORK`; its returned strings are unchanged.
- `app/recommend.py`: `_VERDICT_TIER` and `_VERDICT_REASON` re-key
  `Verdict.UPGRADE.value` → `Verdict.MASTERWORK.value` (tier stays **4**; reason
  string unchanged).

### Frontend

- `src/types.ts`:
  - `Verdict` union: `"upgrade"` → `"masterwork"`.
  - Add a canonical label map:
    ```typescript
    export const VERDICT_LABEL: Record<Verdict, string> = {
      god_roll: "God Roll",
      masterwork: "Masterwork → God Roll",
      good: "Good",
      no_data: "No Data",
      dismantle: "Dismantle",
    };
    ```
- Consumers use `VERDICT_LABEL[w.verdict]` instead of ad-hoc strings/`replace`:
  - `WeaponCard.tsx`: the `BADGE` map's `upgrade` entry becomes `masterwork`
    with `label: VERDICT_LABEL.masterwork` (keep color `#1565c0`); other entries
    may reference `VERDICT_LABEL` for consistency.
  - `WeaponDetail.tsx`: the Verdict line uses `VERDICT_LABEL[w.verdict]` instead
    of `w.verdict.replace("_", " ")`.
  - `ComparePanel.tsx`: the Verdict row uses `VERDICT_LABEL[w.verdict]`.
  - `BuildsPage.tsx`: `VERDICT_RANK` key `upgrade` → `masterwork`; the
    best-weapons filter `w.verdict === "upgrade"` → `"masterwork"`; the verdict
    display at line ~167 uses `VERDICT_LABEL`; the helper text
    "No god-roll / upgrade …" → "No god-roll / masterwork …".
  - `Filters.tsx`: the verdict `<option value="upgrade">Upgrade</option>` →
    `<option value="masterwork">Masterwork → God Roll</option>` (or generated
    from `VERDICT_LABEL`).
- `src/search.ts`: no change — `verdict:` matches the value generically; the
  separate `is:masterwork` token (filters `isMasterworked`) is unaffected.

## Data Flow

```
score_weapon → Verdict.MASTERWORK (value "masterwork")
   → score_by_perks → weapon_to_dict (verdict: "masterwork")
   → WeaponDto.verdict: "masterwork"
   → VERDICT_LABEL["masterwork"] = "Masterwork → God Roll"  (card/detail/compare/builds/filter)
```

## Error Handling

- `VERDICT_LABEL` is keyed by the exact `Verdict` union, so TypeScript flags any
  missing/renamed key at build time — the compiler enforces completeness.
- No persisted data stores the verdict value (it is recomputed each scoring; the
  `weapons_cache` is regenerated post-deploy via recompute-from-cache), so the
  value change is safe.

## Testing

**Backend:**
- `test_perk_scoring.py`: the existing "S-tier not masterworked" test asserts the
  verdict is now `Verdict.MASTERWORK` (and its name is updated).
- `test_explain_verdict.py`: the upgrade-path test uses `Verdict.MASTERWORK`; its
  assertions (reason mentions "not masterworked", path == "Masterwork it → God
  Roll.") are unchanged.
- `test_recommend.py`: fixtures using `verdict="upgrade"` switch to
  `verdict="masterwork"`; ordering assertions unchanged (tier still 4).
- Full backend suite green.

**Frontend:**
- A Vitest test asserting `VERDICT_LABEL.masterwork === "Masterwork → God Roll"`
  and that the map has an entry for every `Verdict` value.
- `npm run build` type-clean (the `Verdict` union change + `Record<Verdict,...>`
  map guarantee all consumers are updated).

## Deploy

After merge: rebuild the frontend, restart the backend, and regenerate the
weapons cache (delete `weapons_cache` KV row → hit an endpoint that triggers
recompute-from-cache) so owned weapons surface the new value. Then verify the
new verdict appears via `/api/weapons`.

## Out of Scope / Future

- Changing the recommendation reason wording for this tier.
- Any new badge color or icon treatment.
