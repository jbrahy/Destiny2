# "Masterwork → God Roll" Verdict Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `upgrade` verdict value with a new `masterwork` value labeled "Masterwork → God Roll", and render all verdict labels from one canonical map.

**Architecture:** A value rename in the backend `Verdict` enum (and its 3 use sites + tests), then a frontend `Verdict` union change plus a single `VERDICT_LABEL` map consumed by every place that displays a verdict.

**Tech Stack:** Python 3.13 + FastAPI + pytest (backend); React + TypeScript + Vitest (frontend).

## Global Constraints

- `upgrade` is fully replaced by `masterwork` — no `upgrade`/`UPGRADE` token remains anywhere.
- New verdict value string is exactly `"masterwork"`; enum member `Verdict.MASTERWORK`; display label exactly `"Masterwork → God Roll"`.
- The trigger logic is unchanged: god-roll perks (S-tier, or ≥2 A/S) AND not masterworked.
- Recommendation tier for the new value stays **4** (ordering unchanged).
- `explain_verdict`'s returned strings are unchanged ("…but not masterworked." / "Masterwork it → God Roll.").
- Badge color stays `#1565c0`.
- `search.ts` is NOT changed.
- Backend tests run from `destiny-weapon-advisor/backend` via `pytest`; frontend from `destiny-weapon-advisor/frontend` via `npm test`.

---

### Task 1: Backend — replace UPGRADE with MASTERWORK

**Files:**
- Modify: `destiny-weapon-advisor/backend/app/models.py` (enum member)
- Modify: `destiny-weapon-advisor/backend/app/perk_scoring.py` (assignment, keepers, explain branch)
- Modify: `destiny-weapon-advisor/backend/app/recommend.py` (tier + reason map keys)
- Modify (tests): `destiny-weapon-advisor/backend/tests/test_perk_scoring.py`, `tests/test_explain_verdict.py`, `tests/test_recommend.py`

**Interfaces:**
- Produces: `Verdict.MASTERWORK` with value `"masterwork"`; `score_weapon`/`score_by_perks` emit it for the not-masterworked-god-roll case; `weapon_to_dict` therefore returns `"verdict": "masterwork"` for those weapons.

- [ ] **Step 1: Update tests to expect the new value (RED)**

In `destiny-weapon-advisor/backend/tests/test_perk_scoring.py`, replace the test:

```python
def test_s_tier_not_masterworked_is_upgrade():
    r = score_by_perks([weapon(["Incandescent"], mw=False)], ratings(SEED))[0]
    assert r["verdict"] == Verdict.UPGRADE
```

with:

```python
def test_s_tier_not_masterworked_is_masterwork():
    r = score_by_perks([weapon(["Incandescent"], mw=False)], ratings(SEED))[0]
    assert r["verdict"] == Verdict.MASTERWORK
```

In `destiny-weapon-advisor/backend/tests/test_explain_verdict.py`, in `test_upgrade_path_is_masterwork`, change the first argument `Verdict.UPGRADE` to `Verdict.MASTERWORK` (leave the rest of the test, including its assertions, unchanged).

In `destiny-weapon-advisor/backend/tests/test_recommend.py`, replace every fixture `verdict="upgrade"` with `verdict="masterwork"` (occurrences in `test_orders_by_verdict_tier` and `test_element_bonus_ties_one_tier_up_then_tiebreakers`). The local names like `name="upg"`/`name="unmatched_upgrade"` and comments may stay; only the `verdict=` string values change. The ordering assertions stay identical (the tier is still 4).

- [ ] **Step 2: Run tests to verify they fail (RED)**

Run: `cd destiny-weapon-advisor/backend && python -m pytest tests/test_perk_scoring.py tests/test_explain_verdict.py tests/test_recommend.py -q`
Expected: FAILs — `Verdict.MASTERWORK` does not exist yet (AttributeError) and/or `score_by_perks` still returns `Verdict.UPGRADE`.

- [ ] **Step 3: Rename the enum member**

In `destiny-weapon-advisor/backend/app/models.py`, in `class Verdict`, change:

```python
    UPGRADE = "upgrade"
```

to:

```python
    MASTERWORK = "masterwork"
```

(Leave the other members and their order untouched.)

- [ ] **Step 4: Update perk_scoring.py**

In `destiny-weapon-advisor/backend/app/perk_scoring.py`:

In `score_weapon`, change:

```python
        verdict = Verdict.GOD_ROLL if weapon.is_masterworked else Verdict.UPGRADE
```

to:

```python
        verdict = Verdict.GOD_ROLL if weapon.is_masterworked else Verdict.MASTERWORK
```

In `explain_verdict`, change the branch header:

```python
    if verdict == Verdict.UPGRADE:
```

to:

```python
    if verdict == Verdict.MASTERWORK:
```

(its body — the reason and `"Masterwork it → God Roll."` path — is unchanged.)

In `score_by_perks`, change the keepers set:

```python
    keepers = {Verdict.GOD_ROLL, Verdict.UPGRADE, Verdict.GOOD}
```

to:

```python
    keepers = {Verdict.GOD_ROLL, Verdict.MASTERWORK, Verdict.GOOD}
```

- [ ] **Step 5: Update recommend.py**

In `destiny-weapon-advisor/backend/app/recommend.py`, change the `_VERDICT_TIER` key:

```python
    Verdict.UPGRADE.value: 4,
```

to:

```python
    Verdict.MASTERWORK.value: 4,
```

and the `_VERDICT_REASON` key:

```python
    Verdict.UPGRADE.value: "Strong roll",
```

to:

```python
    Verdict.MASTERWORK.value: "Strong roll",
```

- [ ] **Step 6: Run the targeted tests to verify GREEN**

Run: `cd destiny-weapon-advisor/backend && python -m pytest tests/test_perk_scoring.py tests/test_explain_verdict.py tests/test_recommend.py -q`
Expected: PASS.

- [ ] **Step 7: Confirm no stray `upgrade`/`UPGRADE` token remains in app code**

Run: `cd destiny-weapon-advisor/backend && grep -rn "UPGRADE\|\"upgrade\"\|'upgrade'" app/ ; echo "exit: $?"`
Expected: no matches in `app/` (grep prints nothing; the `echo` confirms completion). If anything prints, update it to the masterwork equivalent.

- [ ] **Step 8: Run the full backend suite**

Run: `cd destiny-weapon-advisor/backend && python -m pytest -q`
Expected: ALL pass.

- [ ] **Step 9: Commit**

```bash
cd <REPO_ROOT>
git add destiny-weapon-advisor/backend/app/models.py destiny-weapon-advisor/backend/app/perk_scoring.py destiny-weapon-advisor/backend/app/recommend.py destiny-weapon-advisor/backend/tests/test_perk_scoring.py destiny-weapon-advisor/backend/tests/test_explain_verdict.py destiny-weapon-advisor/backend/tests/test_recommend.py
git commit -m "feat: replace 'upgrade' verdict with 'masterwork' (Masterwork -> God Roll)"
```

---

### Task 2: Frontend — masterwork value + canonical VERDICT_LABEL map

**Files:**
- Modify: `destiny-weapon-advisor/frontend/src/types.ts` (union + new `VERDICT_LABEL` export)
- Modify: `destiny-weapon-advisor/frontend/src/components/WeaponCard.tsx` (BADGE map)
- Modify: `destiny-weapon-advisor/frontend/src/components/WeaponDetail.tsx` (verdict line)
- Modify: `destiny-weapon-advisor/frontend/src/components/ComparePanel.tsx` (verdict row)
- Modify: `destiny-weapon-advisor/frontend/src/components/BuildsPage.tsx` (rank, filter, label, text)
- Modify: `destiny-weapon-advisor/frontend/src/components/Filters.tsx` (verdict option)
- Test: `destiny-weapon-advisor/frontend/src/verdict.test.ts`

**Interfaces:**
- Consumes: backend `verdict: "masterwork"` (Task 1).
- Produces: `Verdict` union with `"masterwork"`; `export const VERDICT_LABEL: Record<Verdict, string>` with `masterwork: "Masterwork → God Roll"`.

- [ ] **Step 1: Write the failing test**

```typescript
// destiny-weapon-advisor/frontend/src/verdict.test.ts
import { describe, expect, it } from "vitest";
import { VERDICT_LABEL } from "./types";

describe("VERDICT_LABEL", () => {
  it("labels the masterwork verdict", () => {
    expect(VERDICT_LABEL.masterwork).toBe("Masterwork → God Roll");
  });

  it("has a label for every verdict and no 'upgrade' key", () => {
    expect(Object.keys(VERDICT_LABEL).sort()).toEqual(
      ["dismantle", "god_roll", "good", "masterwork", "no_data"],
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd destiny-weapon-advisor/frontend && npm test -- verdict`
Expected: FAIL — `VERDICT_LABEL` is not exported from `./types`.

- [ ] **Step 3: Update the Verdict union and add VERDICT_LABEL**

In `destiny-weapon-advisor/frontend/src/types.ts`, change line 1:

```typescript
export type Verdict = "god_roll" | "good" | "upgrade" | "no_data" | "dismantle";
```

to:

```typescript
export type Verdict = "god_roll" | "good" | "masterwork" | "no_data" | "dismantle";

export const VERDICT_LABEL: Record<Verdict, string> = {
  god_roll: "God Roll",
  masterwork: "Masterwork → God Roll",
  good: "Good",
  no_data: "No Data",
  dismantle: "Dismantle",
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd destiny-weapon-advisor/frontend && npm test -- verdict`
Expected: PASS (2 tests).

- [ ] **Step 5: Update WeaponCard BADGE map**

In `destiny-weapon-advisor/frontend/src/components/WeaponCard.tsx`, change the import to also pull `VERDICT_LABEL`:

```typescript
import { Verdict, VERDICT_LABEL, WeaponDto } from "../types";
```

and replace the `BADGE` map so its labels come from `VERDICT_LABEL` and the `upgrade` key becomes `masterwork`:

```typescript
const BADGE: Record<Verdict, { label: string; color: string }> = {
  god_roll: { label: VERDICT_LABEL.god_roll, color: "#2e7d32" },
  masterwork: { label: VERDICT_LABEL.masterwork, color: "#1565c0" },
  good: { label: VERDICT_LABEL.good, color: "#f9a825" },
  no_data: { label: VERDICT_LABEL.no_data, color: "#9e9e9e" },
  dismantle: { label: VERDICT_LABEL.dismantle, color: "#c62828" },
};
```

- [ ] **Step 6: Update WeaponDetail verdict line**

In `destiny-weapon-advisor/frontend/src/components/WeaponDetail.tsx`, add `VERDICT_LABEL` to the types import:

```typescript
import { Character, VERDICT_LABEL, WeaponDto } from "../types";
```

and change the verdict line:

```tsx
      <p style={{ margin: "0 0 4px" }}><strong>Verdict:</strong> {w.verdict.replace("_", " ")}</p>
```

to:

```tsx
      <p style={{ margin: "0 0 4px" }}><strong>Verdict:</strong> {VERDICT_LABEL[w.verdict]}</p>
```

- [ ] **Step 7: Update ComparePanel verdict row**

In `destiny-weapon-advisor/frontend/src/components/ComparePanel.tsx`, add `VERDICT_LABEL` to its `../types` import, then change:

```typescript
    { label: "Verdict", get: (w) => w.verdict.replace("_", " ") },
```

to:

```typescript
    { label: "Verdict", get: (w) => VERDICT_LABEL[w.verdict] },
```

- [ ] **Step 8: Update BuildsPage rank, filter, label, and helper text**

In `destiny-weapon-advisor/frontend/src/components/BuildsPage.tsx`:

Add `VERDICT_LABEL` to the `../types` import.

Change the rank map:

```typescript
const VERDICT_RANK: Record<string, number> = { god_roll: 0, upgrade: 1, good: 2 };
```

to:

```typescript
const VERDICT_RANK: Record<string, number> = { god_roll: 0, masterwork: 1, good: 2 };
```

Change the best-weapons filter:

```typescript
      .filter((w) => w.verdict === "god_roll" || w.verdict === "upgrade")
```

to:

```typescript
      .filter((w) => w.verdict === "god_roll" || w.verdict === "masterwork")
```

Change the verdict display at line ~167:

```tsx
                  {" · "}{w.verdict.replace("_", " ")}
```

to:

```tsx
                  {" · "}{VERDICT_LABEL[w.verdict]}
```

Change the helper text:

```
          No god-roll / upgrade {SUBCLASS_ELEMENT[subclass]} (or Kinetic) weapons found in your
```

to:

```
          No god-roll / masterwork {SUBCLASS_ELEMENT[subclass]} (or Kinetic) weapons found in your
```

- [ ] **Step 9: Update the Filters verdict dropdown**

In `destiny-weapon-advisor/frontend/src/components/Filters.tsx`, change the option:

```tsx
        <option value="upgrade">Upgrade</option>
```

to:

```tsx
        <option value="masterwork">Masterwork → God Roll</option>
```

- [ ] **Step 10: Confirm no stray `upgrade` token remains in frontend source**

Run: `cd destiny-weapon-advisor/frontend && grep -rn "upgrade" src/ ; echo "exit: $?"`
Expected: the only matches are `upgradePath` (the unrelated field from the prior feature). No bare `"upgrade"` verdict value or `Upgrade` label should remain. If a bare verdict `upgrade` remains, fix it.

- [ ] **Step 11: Verify build + tests**

Run: `cd destiny-weapon-advisor/frontend && npm run build && npm test`
Expected: build type-clean (the `Record<Verdict, …>` maps force every consumer to be consistent); all Vitest tests PASS.

- [ ] **Step 12: Commit**

```bash
cd <REPO_ROOT>
git add destiny-weapon-advisor/frontend/src/types.ts destiny-weapon-advisor/frontend/src/components/WeaponCard.tsx destiny-weapon-advisor/frontend/src/components/WeaponDetail.tsx destiny-weapon-advisor/frontend/src/components/ComparePanel.tsx destiny-weapon-advisor/frontend/src/components/BuildsPage.tsx destiny-weapon-advisor/frontend/src/components/Filters.tsx destiny-weapon-advisor/frontend/src/verdict.test.ts
git commit -m "feat: 'Masterwork -> God Roll' verdict label via shared VERDICT_LABEL map"
```

---

## Self-Review Notes

- **Spec coverage:** enum rename + scoring + recommend + backend tests (Task 1); Verdict union + VERDICT_LABEL + all 5 consumers + filter + test (Task 2). Deploy step (cache regen) handled post-merge by the controller, as in prior features.
- **Placeholder scan:** none — every step has concrete code/commands.
- **Type consistency:** `Verdict.MASTERWORK` / value `"masterwork"` used identically across models, perk_scoring, recommend (backend) and `"masterwork"` in the TS union + `VERDICT_LABEL` (frontend). Label string `"Masterwork → God Roll"` identical in spec, `VERDICT_LABEL`, and the Filters option.
- **Completeness guard:** Steps 7 (backend) and 10 (frontend) grep for stray `upgrade` tokens; the `Record<Verdict, …>` maps make the TS build fail if any consumer is missed.
- **No behavior change:** trigger logic, recommendation tier (4), explain_verdict text, and badge color all preserved per Global Constraints.
