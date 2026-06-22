# Activity Loadout Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** For a chosen activity, suggest a complete loadout — the best owned weapon per ammo slot plus the seeded subclass build — and let the user apply the weapons to a character in one click.

**Architecture:** A new pure backend function `build_loadout` composes the existing `recommend_weapons` ranking (top weapon per slot) with the seeded subclass build for the activity's recommended class+subclass, and computes simple cross-weapon signals (element coverage). A read-only `GET /api/loadout-suggestion` endpoint serves it. A new "Loadout" view (a mode within the Recommend tab) renders the suggestion and reuses the existing bulk-transfer plumbing to equip the three weapons on a chosen character.

**Tech Stack:** Python 3.13 + FastAPI + pytest (backend); React + TypeScript + Vitest (frontend).

## Design assumptions (called out — confirm if any are wrong)

- **Weapon selection = top-1 per slot** from `recommend_weapons` for the activity context. The ranking is already element-synergy-aware, so no new ranking logic is needed; the builder's new job is composition + coverage signals, not re-ranking.
- **Subclass build** comes from the seeded `builds` keyed `"<recommendedClass>|<recommendedSubclass>"`. If the activity's `recommendedClass` is `Any`, no specific build is attached (show the activity's free-text weapon/notes guidance instead).
- **Cross-weapon constraint for v1 = element-coverage reporting only** (list of distinct weapon elements + whether the activity element is covered). Role balance is implicitly handled by one-weapon-per-slot (Primary=add-clear, Heavy=DPS). No combinatorial optimization in v1 — that is deliberately out of scope (YAGNI).
- **Apply** reuses the existing `bulkMove(items, targetCharacterId, equip=true)` path; it requires the user to pick a target character. No new loadout is persisted (that is the existing Loadouts feature's job).

## Global Constraints

- No new Bungie API calls for *building* the suggestion — consume the existing `weapons_cache` and seeded builds/activities, exactly like `/api/recommendations`.
- Reuse `recommend_weapons` for per-slot ranking — do NOT duplicate ranking logic.
- Ammo slots are exactly: `Primary`, `Special`, `Heavy`.
- Build key format is exactly `"<class>|<subclass>"` (e.g. `"Titan|Solar"`), matching `builds_seed.json`.
- Applying weapons uses the existing transfer/equip endpoints only — no new write scopes.
- Backend tests run from `destiny-weapon-advisor/backend` via `pytest`; frontend tests from `destiny-weapon-advisor/frontend` via `npm test`.

---

### Task 1: `build_loadout` composition function

**Files:**
- Create: `destiny-weapon-advisor/backend/app/loadout_builder.py`
- Test: `destiny-weapon-advisor/backend/tests/test_loadout_builder.py`

**Interfaces:**
- Consumes: `recommend_weapons` and `element_for_subclass` from `app/recommend.py`.
- Produces:
  - `build_loadout(weapons: list[dict], activity: dict, build: dict | None, top_n: int = 5) -> dict`
  - where `activity` is an activity record (keys `name`, `recommendedClass`, `recommendedSubclass`, `weapons`, `notes`) and `build` is the seeded subclass build dict or `None`.
  - Returns:
    ```json
    {
      "activity": "<name>",
      "subclass": {"class": "<class>", "subclass": "<subclass>", "build": <build dict or null>},
      "weapons": {"Primary": <weapon dict or null>, "Special": <...>, "Heavy": <...>},
      "elementCoverage": {"elements": ["Solar", "Void"], "activityElement": "Solar", "matchesActivity": true},
      "guidance": "<activity.weapons free-text>"
    }
    ```

- [ ] **Step 1: Write the failing test**

```python
# destiny-weapon-advisor/backend/tests/test_loadout_builder.py
from app.loadout_builder import build_loadout


def _w(**p):
    base = {
        "name": "Gun", "verdict": "good", "ammoType": "Primary", "element": "Void",
        "matchedPerks": [], "isMasterworked": False, "power": 1800, "instanceId": "i",
        "itemHash": 1,
    }
    base.update(p)
    return base


def _activity(**p):
    base = {
        "name": "Crota's End (Raid)", "recommendedClass": "Titan",
        "recommendedSubclass": "Strand", "weapons": "Sword for Crota; add-clear primary",
        "notes": "n",
    }
    base.update(p)
    return base


BUILD = {"super": "Bladefury", "weapons": "melee-lean"}


def test_picks_top_weapon_per_slot():
    weapons = [
        _w(name="P-good", ammoType="Primary", verdict="good"),
        _w(name="P-god", ammoType="Primary", verdict="god_roll"),
        _w(name="S1", ammoType="Special"),
        _w(name="H1", ammoType="Heavy"),
    ]
    out = build_loadout(weapons, _activity(), BUILD)
    assert out["weapons"]["Primary"]["name"] == "P-god"
    assert out["weapons"]["Special"]["name"] == "S1"
    assert out["weapons"]["Heavy"]["name"] == "H1"


def test_empty_slot_is_null():
    weapons = [_w(name="P1", ammoType="Primary")]
    out = build_loadout(weapons, _activity(), BUILD)
    assert out["weapons"]["Primary"]["name"] == "P1"
    assert out["weapons"]["Special"] is None
    assert out["weapons"]["Heavy"] is None


def test_attaches_subclass_build():
    out = build_loadout([], _activity(recommendedClass="Titan", recommendedSubclass="Strand"), BUILD)
    assert out["subclass"]["class"] == "Titan"
    assert out["subclass"]["subclass"] == "Strand"
    assert out["subclass"]["build"] == BUILD


def test_no_build_when_none_provided():
    out = build_loadout([], _activity(recommendedClass="Any"), None)
    assert out["subclass"]["build"] is None


def test_element_coverage_reports_distinct_elements_and_activity_match():
    weapons = [
        _w(name="P", ammoType="Primary", element="Strand"),
        _w(name="S", ammoType="Special", element="Void"),
        _w(name="H", ammoType="Heavy", element="Strand"),
    ]
    # activity Strand -> Strand element
    out = build_loadout(weapons, _activity(recommendedSubclass="Strand"), BUILD)
    assert sorted(out["elementCoverage"]["elements"]) == ["Strand", "Void"]
    assert out["elementCoverage"]["activityElement"] == "Strand"
    assert out["elementCoverage"]["matchesActivity"] is True


def test_activity_element_none_for_prismatic():
    out = build_loadout([], _activity(recommendedSubclass="Prismatic"), BUILD)
    assert out["elementCoverage"]["activityElement"] is None
    assert out["elementCoverage"]["matchesActivity"] is False


def test_carries_activity_name_and_guidance():
    out = build_loadout([], _activity(name="Last Wish (Raid)", weapons="Tractor Cannon"), BUILD)
    assert out["activity"] == "Last Wish (Raid)"
    assert out["guidance"] == "Tractor Cannon"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd destiny-weapon-advisor/backend && python -m pytest tests/test_loadout_builder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.loadout_builder'`

- [ ] **Step 3: Write minimal implementation**

```python
# destiny-weapon-advisor/backend/app/loadout_builder.py
from app.recommend import element_for_subclass, recommend_weapons

_SLOTS = ("Primary", "Special", "Heavy")


def build_loadout(
    weapons: list[dict], activity: dict, build: dict | None, top_n: int = 5
) -> dict:
    """Compose a full loadout suggestion for an activity: top owned weapon per
    ammo slot (via recommend_weapons) plus the seeded subclass build and simple
    element-coverage signals. Pure — no DB/network."""
    element = element_for_subclass(activity.get("recommendedSubclass", ""))
    ranked = recommend_weapons(
        weapons,
        {"label": activity.get("name", ""), "element": element},
        top_n=top_n,
    )
    chosen = {slot: (ranked["slots"][slot][0] if ranked["slots"][slot] else None) for slot in _SLOTS}

    elements = sorted({c["element"] for c in chosen.values() if c and c.get("element")})
    return {
        "activity": activity.get("name", ""),
        "subclass": {
            "class": activity.get("recommendedClass", ""),
            "subclass": activity.get("recommendedSubclass", ""),
            "build": build,
        },
        "weapons": chosen,
        "elementCoverage": {
            "elements": elements,
            "activityElement": element,
            "matchesActivity": bool(element) and element in elements,
        },
        "guidance": activity.get("weapons", ""),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd destiny-weapon-advisor/backend && python -m pytest tests/test_loadout_builder.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
cd <REPO_ROOT>
git add destiny-weapon-advisor/backend/app/loadout_builder.py destiny-weapon-advisor/backend/tests/test_loadout_builder.py
git commit -m "feat: build_loadout composition for activity loadout builder"
```

---

### Task 2: `GET /api/loadout-suggestion` endpoint

**Files:**
- Modify: `destiny-weapon-advisor/backend/app/main.py` (add import + endpoint)
- Test: `destiny-weapon-advisor/backend/tests/test_loadout_suggestion_api.py`

**Interfaces:**
- Consumes: `build_loadout` (Task 1); existing `kv_get`, `_recompute_from_cache`, `load_activities`, `load_builds`, `get_conn`, `get_settings`, `json`.
- Produces: `GET /api/loadout-suggestion?activity=<name>` returning the `build_loadout` shape. Unknown activity → 404.

- [ ] **Step 1: Write the failing test**

```python
# destiny-weapon-advisor/backend/tests/test_loadout_suggestion_api.py
from fastapi.testclient import TestClient

from app.main import app


def test_unknown_activity_returns_404():
    client = TestClient(app)
    resp = client.get("/api/loadout-suggestion", params={"activity": "Nope"})
    assert resp.status_code == 404


def test_known_activity_returns_suggestion_shape():
    client = TestClient(app)
    # Seeded activities are always present via load_activities.
    resp = client.get("/api/loadout-suggestion", params={"activity": "Crota's End (Raid)"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["activity"] == "Crota's End (Raid)"
    assert set(body["weapons"]) == {"Primary", "Special", "Heavy"}
    assert "subclass" in body and "elementCoverage" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd destiny-weapon-advisor/backend && python -m pytest tests/test_loadout_suggestion_api.py -v`
Expected: FAIL — 404 on the second test (route not defined returns 404 for both, so `test_known_activity_returns_suggestion_shape` fails its 200 assertion).

- [ ] **Step 3: Add the import**

In `destiny-weapon-advisor/backend/app/main.py`, after the existing `from app.recommend import element_for_subclass, recommend_weapons` line, add:

```python
from app.loadout_builder import build_loadout
```

Confirm `load_builds` is in the existing `from app.builds import ...` line (it is imported alongside `load_activities`); no change needed there.

- [ ] **Step 4: Add the endpoint**

In `destiny-weapon-advisor/backend/app/main.py`, immediately after the `recommendations` endpoint function, add:

```python
@app.get("/api/loadout-suggestion")
def loadout_suggestion(activity: str) -> dict:
    settings = get_settings()
    conn = get_conn(settings.db_path)
    activities = load_activities(conn)
    match = next((a for a in activities if a.get("name") == activity), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Unknown activity: {activity}")
    cached = kv_get(conn, "weapons_cache")
    if not cached and _recompute_from_cache(conn):
        cached = kv_get(conn, "weapons_cache")
    weapons_list = json.loads(cached).get("weapons", []) if cached else []
    key = f"{match.get('recommendedClass', '')}|{match.get('recommendedSubclass', '')}"
    build = load_builds(conn).get(key)
    return build_loadout(weapons_list, match, build)
```

Confirm `HTTPException` is already imported in main.py (it is used by other endpoints). If not, add `from fastapi import HTTPException`.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd destiny-weapon-advisor/backend && python -m pytest tests/test_loadout_suggestion_api.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Run the full backend suite**

Run: `cd destiny-weapon-advisor/backend && python -m pytest -q`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
cd <REPO_ROOT>
git add destiny-weapon-advisor/backend/app/main.py destiny-weapon-advisor/backend/tests/test_loadout_suggestion_api.py
git commit -m "feat: GET /api/loadout-suggestion endpoint"
```

---

### Task 3: Frontend API client + types

**Files:**
- Modify: `destiny-weapon-advisor/frontend/src/types.ts` (add `LoadoutSuggestion`)
- Modify: `destiny-weapon-advisor/frontend/src/api.ts` (add `fetchLoadoutSuggestion`)
- Test: `destiny-weapon-advisor/frontend/src/loadoutSuggestion.test.ts`

**Interfaces:**
- Consumes: existing `WeaponDto`, `Build`.
- Produces:
  - ```ts
    export interface LoadoutSuggestion {
      activity: string;
      subclass: { class: string; subclass: string; build: Build | null };
      weapons: Record<"Primary" | "Special" | "Heavy", (WeaponDto & { recommendReason?: string }) | null>;
      elementCoverage: { elements: string[]; activityElement: string | null; matchesActivity: boolean };
      guidance: string;
    }
    ```
  - `fetchLoadoutSuggestion(activity: string): Promise<LoadoutSuggestion>`
  - A pure helper `suggestedItems(s: LoadoutSuggestion): { instanceId: string; itemHash: number }[]` returning the non-null chosen weapons as transfer items (for the Apply button in Task 4).

- [ ] **Step 1: Write the failing test**

```typescript
// destiny-weapon-advisor/frontend/src/loadoutSuggestion.test.ts
import { describe, expect, it } from "vitest";
import { suggestedItems } from "./loadoutSuggestion";
import { LoadoutSuggestion } from "./types";

function weapon(instanceId: string, itemHash: number) {
  return {
    instanceId, itemHash, name: "Gun", weaponType: "Hand Cannon", element: "Void",
    location: "Vault", isMasterworked: false, verdict: "good" as const, matchedPerks: [],
    note: "", tags: [], isDuplicate: false, power: 0, ammoType: "Primary",
    frame: "Adaptive", perkNames: [], stats: {}, ratedPerks: [], icon: "", equipped: false,
  };
}

const base: LoadoutSuggestion = {
  activity: "Raid",
  subclass: { class: "Titan", subclass: "Strand", build: null },
  weapons: { Primary: null, Special: null, Heavy: null },
  elementCoverage: { elements: [], activityElement: null, matchesActivity: false },
  guidance: "",
};

describe("suggestedItems", () => {
  it("returns transfer items for non-null chosen weapons only", () => {
    const s: LoadoutSuggestion = {
      ...base,
      weapons: { Primary: weapon("a", 1), Special: null, Heavy: weapon("c", 3) },
    };
    expect(suggestedItems(s)).toEqual([
      { instanceId: "a", itemHash: 1 },
      { instanceId: "c", itemHash: 3 },
    ]);
  });

  it("returns empty array when no weapons chosen", () => {
    expect(suggestedItems(base)).toEqual([]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd destiny-weapon-advisor/frontend && npm test -- loadoutSuggestion`
Expected: FAIL — cannot resolve `./loadoutSuggestion`.

- [ ] **Step 3: Add the type**

In `destiny-weapon-advisor/frontend/src/types.ts`, append:

```typescript
export interface LoadoutSuggestion {
  activity: string;
  subclass: { class: string; subclass: string; build: Build | null };
  weapons: Record<"Primary" | "Special" | "Heavy", (WeaponDto & { recommendReason?: string }) | null>;
  elementCoverage: { elements: string[]; activityElement: string | null; matchesActivity: boolean };
  guidance: string;
}
```

- [ ] **Step 4: Create the helper**

```typescript
// destiny-weapon-advisor/frontend/src/loadoutSuggestion.ts
import { LoadoutItem, LoadoutSuggestion } from "./types";

const SLOTS: ("Primary" | "Special" | "Heavy")[] = ["Primary", "Special", "Heavy"];

export function suggestedItems(s: LoadoutSuggestion): LoadoutItem[] {
  return SLOTS.map((slot) => s.weapons[slot])
    .filter((w): w is NonNullable<typeof w> => w !== null)
    .map((w) => ({ instanceId: w.instanceId, itemHash: w.itemHash }));
}
```

- [ ] **Step 5: Add the API client function**

In `destiny-weapon-advisor/frontend/src/api.ts`, add `LoadoutSuggestion` to the import from `./types`, then append:

```typescript
export async function fetchLoadoutSuggestion(activity: string): Promise<LoadoutSuggestion> {
  const res = await fetch(`/api/loadout-suggestion?activity=${encodeURIComponent(activity)}`);
  if (!res.ok) throw new Error(`Failed to load loadout suggestion (${res.status})`);
  return (await res.json()) as LoadoutSuggestion;
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd destiny-weapon-advisor/frontend && npm test -- loadoutSuggestion`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
cd <REPO_ROOT>
git add destiny-weapon-advisor/frontend/src/types.ts destiny-weapon-advisor/frontend/src/api.ts destiny-weapon-advisor/frontend/src/loadoutSuggestion.ts destiny-weapon-advisor/frontend/src/loadoutSuggestion.test.ts
git commit -m "feat: frontend loadout-suggestion api + items helper"
```

---

### Task 4: Loadout Builder UI (mode within Recommend tab)

**Files:**
- Create: `destiny-weapon-advisor/frontend/src/components/LoadoutBuilder.tsx`
- Modify: `destiny-weapon-advisor/frontend/src/components/RecommendPage.tsx` (add a "Per-slot" vs "Full loadout" toggle that swaps in the builder)

**Interfaces:**
- Consumes: `fetchActivities`, `fetchLoadoutSuggestion`, `fetchCharacters`, `bulkMove` (api); `suggestedItems` (helper); `WeaponCard` (component); `LoadoutSuggestion`, `ActivityRec`, `Character` (types).
- Produces: a `LoadoutBuilder` component and a view toggle in `RecommendPage`.

- [ ] **Step 1: Create the LoadoutBuilder component**

```tsx
// destiny-weapon-advisor/frontend/src/components/LoadoutBuilder.tsx
import { useEffect, useMemo, useState } from "react";
import { bulkMove, fetchActivities, fetchCharacters, fetchLoadoutSuggestion } from "../api";
import { suggestedItems } from "../loadoutSuggestion";
import { ActivityRec, Character, LoadoutSuggestion } from "../types";
import { WeaponCard } from "./WeaponCard";

const SLOTS: ("Primary" | "Special" | "Heavy")[] = ["Primary", "Special", "Heavy"];

export function LoadoutBuilder() {
  const [activities, setActivities] = useState<ActivityRec[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [activity, setActivity] = useState("");
  const [data, setData] = useState<LoadoutSuggestion | null>(null);
  const [target, setTarget] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    fetchActivities().then((a) => {
      setActivities(a);
      if (a.length) setActivity(a[0].name);
    }).catch(() => setActivities([]));
    fetchCharacters().then((c) => {
      setCharacters(c);
      if (c.length) setTarget(c[0].characterId);
    }).catch(() => setCharacters([]));
  }, []);

  useEffect(() => {
    if (!activity) return;
    setError("");
    setStatus("");
    setData(null);
    fetchLoadoutSuggestion(activity).then(setData).catch((e) => setError(String(e)));
  }, [activity]);

  const items = useMemo(() => (data ? suggestedItems(data) : []), [data]);

  async function apply() {
    if (!data || !target || !items.length) return;
    setStatus("Applying…");
    try {
      const results = await bulkMove(items, target, true);
      const failed = results.filter((r) => !r.ok);
      setStatus(failed.length ? `Applied with ${failed.length} failure(s)` : "Applied ✓");
    } catch (e) {
      setStatus("");
      setError(String(e));
    }
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
        <select value={activity} onChange={(e) => setActivity(e.target.value)}
          style={{ background: "var(--panel)", color: "inherit", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 10px" }}>
          {activities.map((a) => <option key={a.name} value={a.name}>{a.name}</option>)}
        </select>
        <select value={target} onChange={(e) => setTarget(e.target.value)}
          style={{ background: "var(--panel)", color: "inherit", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 10px" }}>
          {characters.map((c) => <option key={c.characterId} value={c.characterId}>{c.className} ({c.light})</option>)}
        </select>
        <button onClick={apply} disabled={!items.length || !target}
          style={{ background: "var(--accent)", color: "#0a0e16", border: "none", borderRadius: 6, padding: "6px 14px", cursor: items.length ? "pointer" : "default", fontWeight: 700 }}>
          Equip weapons
        </button>
        {status && <span style={{ alignSelf: "center", color: "var(--muted)" }}>{status}</span>}
      </div>

      {error && <p style={{ color: "#c62828" }}>{error}</p>}

      {data && (
        <>
          <section style={{ marginBottom: 20 }}>
            <h2 style={{ borderBottom: "1px solid var(--border)", paddingBottom: 6 }}>
              Subclass: {data.subclass.class} {data.subclass.subclass}
            </h2>
            {data.subclass.build ? (
              <dl style={{ display: "grid", gridTemplateColumns: "max-content 1fr", gap: "2px 12px", margin: 0 }}>
                {Object.entries(data.subclass.build).map(([k, v]) => (
                  <div key={k} style={{ display: "contents" }}>
                    <dt style={{ color: "var(--muted)", textTransform: "capitalize" }}>{k}</dt>
                    <dd style={{ margin: 0 }}>{v}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p style={{ color: "var(--muted)" }}>No specific subclass build for this activity.</p>
            )}
          </section>

          <p style={{ color: "var(--muted)" }}>
            Element coverage: {data.elementCoverage.elements.join(", ") || "—"}
            {data.elementCoverage.activityElement &&
              ` · activity favors ${data.elementCoverage.activityElement}` +
              (data.elementCoverage.matchesActivity ? " ✓" : " (not covered)")}
          </p>

          {data.guidance && <p style={{ color: "var(--muted)", fontStyle: "italic" }}>{data.guidance}</p>}

          {SLOTS.map((slot) => (
            <section key={slot} style={{ marginBottom: 16 }}>
              <h3 style={{ margin: "8px 0" }}>{slot}</h3>
              {data.weapons[slot] ? (
                <WeaponCard w={data.weapons[slot]!} onClick={() => {}} />
              ) : (
                <p style={{ color: "var(--muted)" }}>No qualifying weapon owned.</p>
              )}
            </section>
          ))}
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Add a view toggle in RecommendPage**

In `destiny-weapon-advisor/frontend/src/components/RecommendPage.tsx`:

Add the import near the top:

```typescript
import { LoadoutBuilder } from "./LoadoutBuilder";
```

Add a `view` state right after the existing `useState` declarations:

```typescript
  const [view, setView] = useState<"slots" | "loadout">("slots");
```

Add a toggle immediately inside the top-level returned `<div>`, before the existing heading row:

```tsx
      <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
        {(["slots", "loadout"] as const).map((v) => (
          <button key={v} onClick={() => setView(v)}
            style={{
              background: "transparent", border: "none",
              color: view === v ? "var(--accent)" : "var(--muted)",
              fontWeight: view === v ? 700 : 500,
              borderBottom: `2px solid ${view === v ? "var(--accent)" : "transparent"}`,
              padding: "4px 8px", cursor: "pointer", textTransform: "uppercase", letterSpacing: "0.05em",
            }}>
            {v === "slots" ? "Best per slot" : "Full loadout"}
          </button>
        ))}
      </div>

      {view === "loadout" && <LoadoutBuilder />}
```

Wrap the EXISTING per-slot content (the heading row, the PvP note, the error, and the `data && SLOTS.map(...)` block) so it only renders when `view === "slots"`. Concretely, change the existing fragment to be guarded: place `{view === "slots" && (<>` before the existing heading-row `<div>` and `</>)}` after the existing slot-sections block.

- [ ] **Step 3: Verify the build and tests pass**

Run: `cd destiny-weapon-advisor/frontend && npm run build && npm test`
Expected: build succeeds (no TS errors); all Vitest tests PASS.

- [ ] **Step 4: Commit**

```bash
cd <REPO_ROOT>
git add destiny-weapon-advisor/frontend/src/components/LoadoutBuilder.tsx destiny-weapon-advisor/frontend/src/components/RecommendPage.tsx
git commit -m "feat: Activity Loadout Builder UI with equip-to-character"
```

---

## Self-Review Notes

- **Spec coverage:** composition + element coverage (Task 1), endpoint + 404 + cache reuse (Task 2), types + API + items helper (Task 3), UI with subclass build + per-slot weapons + element coverage + equip-to-character (Task 4). Apply reuses existing `bulkMove` (no new write path).
- **Type consistency:** `build_loadout` signature/shape identical Task 1↔2; `LoadoutSuggestion`/`fetchLoadoutSuggestion`/`suggestedItems` identical Task 3↔4; slot strings and build-key format consistent across backend and frontend.
- **Assumptions** (top-1 per slot, coverage-only constraint, no persisted loadout) are listed at the top — confirm before executing if any are wrong.
- **Open question for executor:** verify `Character` type has a `characterId` field (used by the target dropdown and `bulkMove`); the existing `fetchCharacters`/Loadouts feature already relies on it, so it should be present — confirm during Task 4.
