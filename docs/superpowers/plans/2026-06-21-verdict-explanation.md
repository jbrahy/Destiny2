# Weapon Verdict Explanation + Upgrade Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show, in the weapon detail panel, why each weapon's verdict was selected and what reaching the next tier would take; plus a macOS launcher app to start the advisor from the Dock.

**Architecture:** A pure `explain_verdict` function lives beside the verdict rules in `app/perk_scoring.py`, is called in `score_by_perks` after the dupe-demotion pass, and its two strings (`verdictReason`, `upgradePath`) flow through `weapon_to_dict` → `WeaponDto` → `WeaponDetail`. A separate installer script generates a double-clickable `.app` bundle.

**Tech Stack:** Python 3.13 + FastAPI + pytest (backend); React + TypeScript + Vitest (frontend); bash + macOS `.app` bundle (launcher).

## Global Constraints

- The explanation must be derived from the same inputs/thresholds as the verdict — no separate rule copy. `TIER_SCORE = {S:5, A:4, B:3, C:2, D:1}`; "strong" perk = rated A or S (score ≥ 4).
- `upgradePath` is `None`/`null` for God Roll and for a dupe-demoted Dismantle; a string otherwise.
- Random-roll-only suffix `" (re-roll/craft for a better roll)"` is appended ONLY to perk-improvement paths, never to the masterwork path.
- Explanation appears only in `WeaponDetail`; `WeaponCard`/grid is unchanged.
- No new Bungie calls — derived from already-scored data.
- Backend tests run from `destiny-weapon-advisor/backend` via `pytest`; frontend from `destiny-weapon-advisor/frontend` via `npm test`.

---

### Task 1: `explain_verdict` + wiring into scoring

**Files:**
- Modify: `destiny-weapon-advisor/backend/app/perk_scoring.py` (add `explain_verdict`, populate fields in `score_by_perks`)
- Modify: `destiny-weapon-advisor/backend/app/main.py` (add two fields in `weapon_to_dict`)
- Test: `destiny-weapon-advisor/backend/tests/test_explain_verdict.py`

**Interfaces:**
- Consumes: `Verdict` (from `app.models`), `TIER_SCORE` (already imported in perk_scoring.py).
- Produces:
  - `explain_verdict(verdict, rated, is_masterworked, is_random_roll, dupe_demoted) -> tuple[str, str | None]`
  - `score_by_perks` result dicts gain `"verdictReason": str` and `"upgradePath": str | None`.
  - `weapon_to_dict` output gains `"verdictReason"` and `"upgradePath"`.

- [ ] **Step 1: Write the failing test**

```python
# destiny-weapon-advisor/backend/tests/test_explain_verdict.py
from app.models import Verdict
from app.perk_scoring import explain_verdict


def _rated(*pairs):
    # pairs: (name, rating). Returned best-first is the caller's job; tests pass sorted.
    return [{"name": n, "rating": r, "reason": "", "tags": []} for n, r in pairs]


def test_god_roll_reason_and_no_upgrade_path():
    reason, upgrade = explain_verdict(
        Verdict.GOD_ROLL, _rated(("Frenzy", "S"), ("Killing Wind", "A")),
        is_masterworked=True, is_random_roll=True, dupe_demoted=False,
    )
    assert "Frenzy" in reason and "masterworked" in reason
    assert upgrade is None


def test_upgrade_path_is_masterwork():
    reason, upgrade = explain_verdict(
        Verdict.UPGRADE, _rated(("Frenzy", "S"), ("Killing Wind", "A")),
        is_masterworked=False, is_random_roll=True, dupe_demoted=False,
    )
    assert "not masterworked" in reason
    assert upgrade == "Masterwork it → God Roll."


def test_good_path_mentions_second_strong_perk_and_reroll_for_random():
    reason, upgrade = explain_verdict(
        Verdict.GOOD, _rated(("Outlaw", "B")),
        is_masterworked=False, is_random_roll=True, dupe_demoted=False,
    )
    assert "B-tier" in reason and "Outlaw" in reason
    assert upgrade.startswith("A second A/S-tier perk")
    assert "re-roll/craft" in upgrade


def test_good_path_no_reroll_suffix_for_fixed_roll():
    _, upgrade = explain_verdict(
        Verdict.GOOD, _rated(("Outlaw", "B")),
        is_masterworked=False, is_random_roll=False, dupe_demoted=False,
    )
    assert "re-roll/craft" not in upgrade


def test_no_data_empty_vs_c_tier():
    empty_reason, empty_up = explain_verdict(
        Verdict.NO_DATA, [], is_masterworked=False, is_random_roll=True, dupe_demoted=False,
    )
    assert "No perk-rating data" in empty_reason
    assert empty_up == "Rate its perks on the Perks tab."

    c_reason, c_up = explain_verdict(
        Verdict.NO_DATA, _rated(("Some Perk", "C")),
        is_masterworked=False, is_random_roll=True, dupe_demoted=False,
    )
    assert "C-tier" in c_reason
    assert c_up.startswith("Any A- or B-tier perk → Good")


def test_dismantle_dupe_vs_d_tier():
    dupe_reason, dupe_up = explain_verdict(
        Verdict.DISMANTLE, _rated(("Bad Perk", "D")),
        is_masterworked=False, is_random_roll=True, dupe_demoted=True,
    )
    assert "better-perked copy" in dupe_reason
    assert dupe_up is None

    d_reason, d_up = explain_verdict(
        Verdict.DISMANTLE, _rated(("Bad Perk", "D")),
        is_masterworked=False, is_random_roll=False, dupe_demoted=False,
    )
    assert "D-tier" in d_reason
    assert d_up == "Any A/B-tier perk → Good"


def test_unknown_verdict_is_safe():
    assert explain_verdict("weird", [], False, False, False) == ("", None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd destiny-weapon-advisor/backend && python -m pytest tests/test_explain_verdict.py -v`
Expected: FAIL with `ImportError: cannot import name 'explain_verdict'`.

- [ ] **Step 3: Implement `explain_verdict`**

In `destiny-weapon-advisor/backend/app/perk_scoring.py`, add this function (after the imports, before `score_weapon`):

```python
def explain_verdict(
    verdict, rated: list[dict], is_masterworked: bool,
    is_random_roll: bool, dupe_demoted: bool,
) -> tuple[str, str | None]:
    """Explain why `verdict` was chosen and what reaching the next tier takes.
    Derived from the same thresholds score_weapon uses, so it cannot drift."""
    reroll = " (re-roll/craft for a better roll)" if is_random_roll else ""
    strong = [r["name"] for r in rated if TIER_SCORE.get(r["rating"], 0) >= 4]

    if verdict == Verdict.GOD_ROLL:
        names = ", ".join(strong) or "strong perks"
        return f"Top-tier perks ({names}) and masterworked.", None
    if verdict == Verdict.UPGRADE:
        names = ", ".join(strong) or "strong perks"
        return (f"{len(strong)} A/S-tier perk(s) ({names}) but not masterworked.",
                "Masterwork it → God Roll.")
    if verdict == Verdict.GOOD:
        best = rated[0] if rated else None
        reason = (
            f"Best perk is {best['rating']}-tier ({best['name']}); "
            "no S-tier and fewer than two A/S perks."
            if best else "No S-tier and fewer than two A/S perks."
        )
        return reason, f"A second A/S-tier perk (or one S-tier perk) → Upgrade{reroll}"
    if verdict == Verdict.NO_DATA:
        if not rated:
            return ("No perk-rating data for this weapon's perks.",
                    "Rate its perks on the Perks tab.")
        return "Only C-tier perks for this weapon type.", f"Any A- or B-tier perk → Good{reroll}"
    if verdict == Verdict.DISMANTLE:
        if dupe_demoted:
            return "A better-perked copy of this weapon exists in your inventory.", None
        return "Only low-value (D-tier) perks.", f"Any A/B-tier perk → Good{reroll}"
    return "", None
```

- [ ] **Step 4: Run the explain test to verify it passes**

Run: `cd destiny-weapon-advisor/backend && python -m pytest tests/test_explain_verdict.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Wire into `score_by_perks`**

In `destiny-weapon-advisor/backend/app/perk_scoring.py`, in `score_by_perks`, the dupe-demotion loop currently sets `r["verdict"] = Verdict.DISMANTLE` and `r["note"] = ...`. In that same `if` block, add a flag:

```python
            r["verdict"] = Verdict.DISMANTLE
            r["note"] = "A better-perked copy of this weapon exists in your inventory."
            r["dupe_demoted"] = True
```

Then, immediately before `return results` at the end of `score_by_perks`, add:

```python
    for r in results:
        reason, upgrade = explain_verdict(
            r["verdict"], r["rated"], r["weapon"].is_masterworked,
            r["weapon"].is_random_roll, r.get("dupe_demoted", False),
        )
        r["verdictReason"] = reason
        r["upgradePath"] = upgrade
    return results
```

- [ ] **Step 6: Expose the fields in `weapon_to_dict`**

In `destiny-weapon-advisor/backend/app/main.py`, in `weapon_to_dict`, add two entries to the returned dict (next to `"note": info["note"],`):

```python
        "verdictReason": info.get("verdictReason", ""),
        "upgradePath": info.get("upgradePath"),
```

- [ ] **Step 7: Add an integration test for the wiring**

Append to `destiny-weapon-advisor/backend/tests/test_explain_verdict.py`:

```python
from app.models import OwnedWeapon
from app.perk_ratings import PerkRatings
from app.perk_scoring import score_by_perks


def _ratings(mapping):
    # mapping: {perk_name: rating}. Build a PerkRatings that returns it for any type.
    class _R(PerkRatings):
        def __init__(self):
            pass
        def get(self, name, weapon_type):
            r = mapping.get(name)
            return {"rating": r, "reason": "", "tags": []} if r else None
    return _R()


def _weapon(instance_id, perks, mw=False, random=True, item_hash=1):
    return OwnedWeapon(
        instance_id=instance_id, item_hash=item_hash, name="Gun", weapon_type="Hand Cannon",
        element="Void", is_masterworked=mw, is_random_roll=random, perks=frozenset(),
        location="Vault", perk_names=perks,
    )


def test_score_by_perks_populates_explanation_fields():
    ratings = _ratings({"Frenzy": "S", "Outlaw": "B"})
    results = score_by_perks([_weapon("a", ["Frenzy"], mw=False)], ratings)
    r = results[0]
    assert r["verdictReason"]
    assert r["upgradePath"] == "Masterwork it → God Roll."  # S perk, not masterworked → Upgrade
```

- [ ] **Step 8: Run the full backend suite**

Run: `cd destiny-weapon-advisor/backend && python -m pytest -q`
Expected: ALL pass.

- [ ] **Step 9: Commit**

```bash
cd <REPO_ROOT>
git add destiny-weapon-advisor/backend/app/perk_scoring.py destiny-weapon-advisor/backend/app/main.py destiny-weapon-advisor/backend/tests/test_explain_verdict.py
git commit -m "feat: explain_verdict reason + upgrade path on scored weapons"
```

---

### Task 2: Surface reason + upgrade path in WeaponDetail

**Files:**
- Modify: `destiny-weapon-advisor/frontend/src/types.ts` (add two `WeaponDto` fields)
- Modify: `destiny-weapon-advisor/frontend/src/components/WeaponDetail.tsx` (render the block)
- Modify: `destiny-weapon-advisor/frontend/src/search.test.ts` (extend the `weapon()` factory so the suite stays type-correct)

**Interfaces:**
- Consumes: backend `verdictReason: string` and `upgradePath: string | null` on each weapon dict (Task 1).
- Produces: `WeaponDto.verdictReason: string`, `WeaponDto.upgradePath: string | null`; a rendered reason + optional upgrade-path line in `WeaponDetail`.

- [ ] **Step 1: Add the WeaponDto fields**

In `destiny-weapon-advisor/frontend/src/types.ts`, inside `interface WeaponDto`, add after the `note: string;` line:

```typescript
  verdictReason: string;
  upgradePath: string | null;
```

- [ ] **Step 2: Keep the test factory type-correct (run to see the type error first)**

Run: `cd destiny-weapon-advisor/frontend && npm run build`
Expected: FAIL — `search.test.ts`'s `weapon()` factory object is missing `verdictReason`/`upgradePath` (TS error), OR build passes if TS doesn't check the test's object literal against the full type. If it fails, proceed to Step 3; if it passes, still do Step 3 for correctness.

- [ ] **Step 3: Update the test factory**

In `destiny-weapon-advisor/frontend/src/search.test.ts`, in the `weapon()` helper's returned object, add after `note: "",`:

```typescript
    verdictReason: "", upgradePath: null,
```

- [ ] **Step 4: Render the block in WeaponDetail**

In `destiny-weapon-advisor/frontend/src/components/WeaponDetail.tsx`, find the existing verdict line:

```tsx
      <p style={{ margin: "0 0 4px" }}><strong>Verdict:</strong> {w.verdict.replace("_", " ")}</p>
```

Immediately AFTER it, insert:

```tsx
      {w.verdictReason && (
        <p style={{ margin: "0 0 4px", color: "var(--muted)", fontSize: 13 }}>
          {w.verdictReason}
        </p>
      )}
      {w.upgradePath && (
        <p style={{ margin: "0 0 4px", fontSize: 13 }}>
          <strong style={{ color: "var(--accent)" }}>↑ Upgrade path:</strong> {w.upgradePath}
        </p>
      )}
```

- [ ] **Step 5: Verify build + tests**

Run: `cd destiny-weapon-advisor/frontend && npm run build && npm test`
Expected: build succeeds (no TS errors); all Vitest tests PASS.

- [ ] **Step 6: Commit**

```bash
cd <REPO_ROOT>
git add destiny-weapon-advisor/frontend/src/types.ts destiny-weapon-advisor/frontend/src/components/WeaponDetail.tsx destiny-weapon-advisor/frontend/src/search.test.ts
git commit -m "feat: show verdict reason + upgrade path in weapon detail"
```

Note: no new component test is added — there is no React component-test harness in this project (existing Vitest tests are pure-logic only), and this change is presentational display of backend-provided strings that are fully unit-tested in Task 1. Verification is the type-checked build + the green suite.

---

### Task 3: macOS launcher app (Dock/app-bar)

**Files:**
- Create: `destiny-weapon-advisor/scripts/install-macos-app.sh`

**Interfaces:**
- Produces: an executable installer that generates `~/Applications/Destiny 2 Advisor.app`, a double-clickable bundle that starts the backend (building the frontend first if needed) and opens `https://localhost:8443`.

- [ ] **Step 1: Create the installer script**

Create `destiny-weapon-advisor/scripts/install-macos-app.sh` with:

```bash
#!/usr/bin/env bash
# Generate a double-clickable macOS app (~/Applications/Destiny 2 Advisor.app)
# that launches the Destiny 2 Advisor single-server and opens it in the browser.
# Drag the app from ~/Applications onto your Dock to pin it to the app bar.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"          # destiny-weapon-advisor/
APP_DIR="$HOME/Applications/Destiny 2 Advisor.app"
MACOS_DIR="$APP_DIR/Contents/MacOS"
LOG="$HOME/Library/Logs/destiny2-advisor.log"

echo "==> Installing $APP_DIR"
rm -rf "$APP_DIR"
mkdir -p "$MACOS_DIR"

cat > "$APP_DIR/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Destiny 2 Advisor</string>
  <key>CFBundleDisplayName</key><string>Destiny 2 Advisor</string>
  <key>CFBundleIdentifier</key><string>com.destinyopt.advisor</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>launch</string>
  <key>LSUIElement</key><true/>
</dict>
</plist>
PLIST

# The launcher script baked with this repo's absolute path.
cat > "$MACOS_DIR/launch" <<LAUNCH
#!/usr/bin/env bash
set -uo pipefail
REPO="$REPO"
LOG="$LOG"
URL="https://localhost:8443"

mkdir -p "\$(dirname "\$LOG")"

# Build the frontend once if it has never been built.
if [ ! -d "\$REPO/frontend/dist" ]; then
  ( cd "\$REPO/frontend" && npm install && npm run build ) >>"\$LOG" 2>&1
fi

# Start the backend only if it isn't already responding.
if ! curl -sk -o /dev/null "\$URL/api/health"; then
  ( cd "\$REPO/backend" && nohup python -m app.main >>"\$LOG" 2>&1 & )
fi

# Wait for health, then open the browser.
for _ in \$(seq 1 30); do
  if curl -sk -o /dev/null "\$URL/api/health"; then break; fi
  sleep 1
done
open "\$URL"
LAUNCH

chmod +x "$MACOS_DIR/launch"

echo "==> Done."
echo "    Open it from Spotlight/Launchpad ('Destiny 2 Advisor'), or open ~/Applications and"
echo "    drag it onto your Dock to pin it to the app bar."
echo "    Logs: $LOG"
echo "    To stop the server: pkill -f 'app.main'"
```

- [ ] **Step 2: Make it executable and syntax-check both scripts**

Run:
```bash
cd <REPO_ROOT>/destiny-weapon-advisor
chmod +x scripts/install-macos-app.sh
bash -n scripts/install-macos-app.sh && echo "installer syntax OK"
```
Expected: prints `installer syntax OK` (no syntax errors).

- [ ] **Step 3: Run the installer and verify the bundle**

Run:
```bash
cd <REPO_ROOT>/destiny-weapon-advisor
./scripts/install-macos-app.sh
test -x "$HOME/Applications/Destiny 2 Advisor.app/Contents/MacOS/launch" && echo "launch executable OK"
test -f "$HOME/Applications/Destiny 2 Advisor.app/Contents/Info.plist" && echo "Info.plist OK"
bash -n "$HOME/Applications/Destiny 2 Advisor.app/Contents/MacOS/launch" && echo "launch syntax OK"
```
Expected: prints `launch executable OK`, `Info.plist OK`, `launch syntax OK`, and the installer's "Done." messaging with the correct repo path baked in.

- [ ] **Step 4: Commit**

```bash
cd <REPO_ROOT>
git add destiny-weapon-advisor/scripts/install-macos-app.sh
git commit -m "feat: macOS launcher app installer for the Dock"
```

---

## Self-Review Notes

- **Spec coverage:** `explain_verdict` for all 5 verdicts + empty-rated + dupe-demoted + random-vs-fixed (Task 1 Steps 1–4); wiring into `score_by_perks` after the dupe pass + `weapon_to_dict` fields + integration test (Task 1 Steps 5–8); `WeaponDto` fields + detail render with the upgrade line hidden when null (Task 2). The launcher app (extra user request) is Task 3.
- **Placeholder scan:** none — all steps carry complete code/commands.
- **Type consistency:** `verdictReason`/`upgradePath` names identical across backend (`explain_verdict`, `score_by_perks`, `weapon_to_dict`) and frontend (`WeaponDto`, `WeaponDetail`). `upgradePath` is `str | None` (backend) ↔ `string | null` (TS).
- **Dupe-demotion:** `dupe_demoted` flag set in the existing demotion branch and read by the post-pass; default `False` via `.get`.
- **Deploy note (post-merge):** rebuild the frontend and restart the backend so the new fields + routes are served (the running process must be restarted to pick up backend changes).
