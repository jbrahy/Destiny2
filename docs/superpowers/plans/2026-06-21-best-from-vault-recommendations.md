# Best-from-Vault Weapon Recommendations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** For a chosen context (general PvE/PvP or a specific activity), rank the weapons the user already owns, grouped by ammo slot, in a new "Recommend" tab.

**Architecture:** A new pure backend function `recommend_weapons` ranks the already-cached scored weapons (no new Bungie calls). A read-only `GET /api/recommendations` endpoint resolves the context and calls it. A new React "Recommend" tab renders the grouped results reusing the existing `WeaponCard`.

**Tech Stack:** Python 3.13 + FastAPI + pytest (backend); React + TypeScript + Vitest (frontend).

## Global Constraints

- No new Bungie API calls — consume the existing `weapons_cache` in SQLite KV.
- DISMANTLE-tier weapons are excluded from all recommendations.
- General PvP uses the same quality ranking as PvE (element bonus off) for v1.
- Verdict string values are exactly: `god_roll`, `upgrade`, `good`, `no_data`, `dismantle` (from `app/models.py` `Verdict`).
- Ammo slots are exactly: `Primary`, `Special`, `Heavy`.
- Backend tests run from `destiny-weapon-advisor/backend` via `pytest`. Frontend tests run from `destiny-weapon-advisor/frontend` via `npm test`.

---

### Task 1: `recommend_weapons` ranking engine

**Files:**
- Create: `destiny-weapon-advisor/backend/app/recommend.py`
- Test: `destiny-weapon-advisor/backend/tests/test_recommend.py`

**Interfaces:**
- Consumes: scored weapon dicts shaped like `weapon_to_dict` output (keys: `verdict`, `ammoType`, `element`, `matchedPerks`, `isMasterworked`, `power`, `name`).
- Produces:
  - `element_for_subclass(subclass: str) -> str | None`
  - `recommend_weapons(weapons: list[dict], context: dict, top_n: int = 5) -> dict` where `context` is `{"label": str, "element": str | None}`, returning `{"context": str, "slots": {"Primary": [...], "Special": [...], "Heavy": [...]}}`. Each weapon dict is the input dict plus a `recommendReason` string; no internal sort keys leak.

- [ ] **Step 1: Write the failing test**

```python
# destiny-weapon-advisor/backend/tests/test_recommend.py
from app.recommend import element_for_subclass, recommend_weapons


def _w(**p):
    base = {
        "name": "Gun", "verdict": "good", "ammoType": "Primary", "element": "Void",
        "matchedPerks": [], "isMasterworked": False, "power": 1800,
    }
    base.update(p)
    return base


GENERAL = {"label": "General (PvE)", "element": None}


def test_element_for_subclass_maps_damage_types():
    assert element_for_subclass("Solar") == "Solar"
    assert element_for_subclass("Prismatic") is None
    assert element_for_subclass("Any") is None
    assert element_for_subclass("") is None


def test_groups_by_ammo_slot():
    weapons = [_w(name="P", ammoType="Primary"), _w(name="S", ammoType="Special"),
               _w(name="H", ammoType="Heavy")]
    out = recommend_weapons(weapons, GENERAL)
    assert [w["name"] for w in out["slots"]["Primary"]] == ["P"]
    assert [w["name"] for w in out["slots"]["Special"]] == ["S"]
    assert [w["name"] for w in out["slots"]["Heavy"]] == ["H"]


def test_orders_by_verdict_tier():
    weapons = [_w(name="good", verdict="good"), _w(name="god", verdict="god_roll"),
               _w(name="upg", verdict="upgrade")]
    out = recommend_weapons(weapons, GENERAL)
    assert [w["name"] for w in out["slots"]["Primary"]] == ["god", "upg", "good"]


def test_excludes_dismantle():
    weapons = [_w(name="keep", verdict="good"), _w(name="trash", verdict="dismantle")]
    out = recommend_weapons(weapons, GENERAL)
    assert [w["name"] for w in out["slots"]["Primary"]] == ["keep"]


def test_activity_element_bonus_beats_higher_base():
    # base "good"(3)+match(1)=4 should beat "upgrade"(4)+0=4? No — tie, then tiebreakers.
    # Use clear case: matched "good" (3+1=4) beats unmatched "good" (3).
    activity = {"label": "Raid", "element": "Solar"}
    weapons = [_w(name="solar", verdict="good", element="Solar"),
               _w(name="void", verdict="good", element="Void")]
    out = recommend_weapons(weapons, activity)
    assert [w["name"] for w in out["slots"]["Primary"]] == ["solar", "void"]
    assert "element-matched for Solar" in out["slots"]["Primary"][0]["recommendReason"]


def test_general_context_no_element_bonus():
    weapons = [_w(name="void", verdict="good", element="Void"),
               _w(name="solar", verdict="good", element="Solar")]
    out = recommend_weapons(weapons, GENERAL)
    # tie on verdict; name tiebreaker -> alphabetical
    assert [w["name"] for w in out["slots"]["Primary"]] == ["solar", "void"]
    assert out["slots"]["Primary"][0]["recommendReason"] == "Good roll"


def test_masterwork_and_power_tiebreakers():
    weapons = [_w(name="plain", isMasterworked=False, power=1800),
               _w(name="mw", isMasterworked=True, power=1800)]
    out = recommend_weapons(weapons, GENERAL)
    assert [w["name"] for w in out["slots"]["Primary"]] == ["mw", "plain"]


def test_empty_input_returns_empty_slots():
    out = recommend_weapons([], GENERAL)
    assert out["slots"] == {"Primary": [], "Special": [], "Heavy": []}


def test_top_n_truncates():
    weapons = [_w(name=f"g{i}", verdict="good") for i in range(7)]
    out = recommend_weapons(weapons, GENERAL, top_n=3)
    assert len(out["slots"]["Primary"]) == 3


def test_no_internal_rank_key_leaks():
    out = recommend_weapons([_w()], GENERAL)
    assert "_rank" not in out["slots"]["Primary"][0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd destiny-weapon-advisor/backend && python -m pytest tests/test_recommend.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.recommend'`

- [ ] **Step 3: Write minimal implementation**

```python
# destiny-weapon-advisor/backend/app/recommend.py
from app.models import Verdict

_VERDICT_TIER = {
    Verdict.GOD_ROLL.value: 5,
    Verdict.UPGRADE.value: 4,
    Verdict.GOOD.value: 3,
    Verdict.NO_DATA.value: 1,
    Verdict.DISMANTLE.value: 0,
}

_VERDICT_REASON = {
    Verdict.GOD_ROLL.value: "God roll",
    Verdict.UPGRADE.value: "Strong roll",
    Verdict.GOOD.value: "Good roll",
    Verdict.NO_DATA.value: "Usable",
}

_SUBCLASS_ELEMENT = {
    "Solar": "Solar", "Arc": "Arc", "Void": "Void",
    "Stasis": "Stasis", "Strand": "Strand",
}

_SLOTS = ("Primary", "Special", "Heavy")


def element_for_subclass(subclass: str) -> str | None:
    """Map a subclass name to its damage element, or None for Prismatic/Any/unknown."""
    return _SUBCLASS_ELEMENT.get(subclass)


def recommend_weapons(weapons: list[dict], context: dict, top_n: int = 5) -> dict:
    """Rank owned weapons per ammo slot for a context.

    context: {"label": str, "element": str | None}. element is set only for
    activity contexts that resolve to a damage element; it grants a synergy bonus.
    """
    element = context.get("element")
    slots: dict[str, list[dict]] = {s: [] for s in _SLOTS}
    for w in weapons:
        base = _VERDICT_TIER.get(w.get("verdict"), 0)
        if base <= 0:  # DISMANTLE or unknown verdict
            continue
        ammo = w.get("ammoType")
        if ammo not in slots:
            continue
        matched = bool(element) and w.get("element") == element
        effective = base + (1 if matched else 0)
        reasons = [_VERDICT_REASON.get(w.get("verdict"), "")]
        if matched:
            reasons.append(f"element-matched for {element}")
        entry = dict(w)
        entry["recommendReason"] = " • ".join(r for r in reasons if r)
        entry["_rank"] = (
            -effective,
            -len(w.get("matchedPerks", [])),
            0 if w.get("isMasterworked") else 1,
            -int(w.get("power", 0)),
            w.get("name", ""),
        )
        slots[ammo].append(entry)
    for slot, entries in slots.items():
        entries.sort(key=lambda e: e["_rank"])
        slots[slot] = entries[:top_n]
        for e in slots[slot]:
            del e["_rank"]
    return {"context": context.get("label", ""), "slots": slots}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd destiny-weapon-advisor/backend && python -m pytest tests/test_recommend.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
cd <REPO_ROOT>
git add destiny-weapon-advisor/backend/app/recommend.py destiny-weapon-advisor/backend/tests/test_recommend.py
git commit -m "feat: recommend_weapons ranking engine for best-from-vault recs"
```

---

### Task 2: `GET /api/recommendations` endpoint

**Files:**
- Modify: `destiny-weapon-advisor/backend/app/main.py` (add import + endpoint; reuse `kv_get`, `_recompute_from_cache`, `load_activities`)
- Test: `destiny-weapon-advisor/backend/tests/test_recommend_api.py`

**Interfaces:**
- Consumes: `recommend_weapons`, `element_for_subclass` from Task 1; existing `kv_get`, `_recompute_from_cache`, `load_activities`, `get_conn`, `get_settings`.
- Produces: `GET /api/recommendations?context=<general-pve|general-pvp|activity name>` returning the `recommend_weapons` shape. Default `context=general-pve`.

- [ ] **Step 1: Write the failing test**

```python
# destiny-weapon-advisor/backend/tests/test_recommend_api.py
from fastapi.testclient import TestClient

from app.main import app


def test_recommendations_default_context_ok():
    client = TestClient(app)
    resp = client.get("/api/recommendations")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["slots"]) == {"Primary", "Special", "Heavy"}
    assert body["context"] == "General (PvE)"


def test_recommendations_pvp_context_label():
    client = TestClient(app)
    resp = client.get("/api/recommendations", params={"context": "general-pvp"})
    assert resp.status_code == 200
    assert resp.json()["context"] == "General (PvP)"


def test_recommendations_unknown_context_falls_back():
    client = TestClient(app)
    resp = client.get("/api/recommendations", params={"context": "Nonexistent Activity"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["context"] == "Nonexistent Activity"
    assert set(body["slots"]) == {"Primary", "Special", "Heavy"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd destiny-weapon-advisor/backend && python -m pytest tests/test_recommend_api.py -v`
Expected: FAIL with 404 (route not defined) on the assertions.

- [ ] **Step 3: Add the import**

In `destiny-weapon-advisor/backend/app/main.py`, add after the existing `from app.perk_scoring import score_by_perks` line (line ~22):

```python
from app.recommend import element_for_subclass, recommend_weapons
```

- [ ] **Step 4: Add the endpoint and context resolver**

In `destiny-weapon-advisor/backend/app/main.py`, immediately after the `weapons` endpoint function (the block ending with `return _compute_weapons(conn, manifest, profile)`), add:

```python
def _resolve_rec_context(conn, context: str) -> dict:
    if context == "general-pve":
        return {"label": "General (PvE)", "element": None}
    if context == "general-pvp":
        return {"label": "General (PvP)", "element": None}
    for activity in load_activities(conn):
        if activity.get("name") == context:
            return {
                "label": activity["name"],
                "element": element_for_subclass(activity.get("recommendedSubclass", "")),
            }
    return {"label": context, "element": None}


@app.get("/api/recommendations")
def recommendations(context: str = "general-pve") -> dict:
    settings = get_settings()
    conn = get_conn(settings.db_path)
    cached = kv_get(conn, "weapons_cache")
    if not cached and _recompute_from_cache(conn):
        cached = kv_get(conn, "weapons_cache")
    weapons_list = json.loads(cached)["weapons"] if cached else []
    ctx = _resolve_rec_context(conn, context)
    return recommend_weapons(weapons_list, ctx)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd destiny-weapon-advisor/backend && python -m pytest tests/test_recommend_api.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Run the full backend suite (no regressions)**

Run: `cd destiny-weapon-advisor/backend && python -m pytest -q`
Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
cd <REPO_ROOT>
git add destiny-weapon-advisor/backend/app/main.py destiny-weapon-advisor/backend/tests/test_recommend_api.py
git commit -m "feat: GET /api/recommendations endpoint"
```

---

### Task 3: Frontend API client, types, and context-options helper

**Files:**
- Modify: `destiny-weapon-advisor/frontend/src/types.ts` (add `Recommendations`, `RecommendedWeapon`)
- Modify: `destiny-weapon-advisor/frontend/src/api.ts` (add `fetchRecommendations`)
- Create: `destiny-weapon-advisor/frontend/src/recommend.ts` (pure `buildContextOptions`)
- Test: `destiny-weapon-advisor/frontend/src/recommend.test.ts`

**Interfaces:**
- Consumes: existing `WeaponDto`, `ActivityRec`, `fetchActivities`.
- Produces:
  - `RecommendedWeapon = WeaponDto & { recommendReason: string }`
  - `Recommendations = { context: string; slots: Record<"Primary" | "Special" | "Heavy", RecommendedWeapon[]> }`
  - `fetchRecommendations(context: string): Promise<Recommendations>`
  - `buildContextOptions(activities: ActivityRec[]): { value: string; label: string }[]` — prepends General (PvE)/(PvP), then one entry per activity (`value` = activity name, `label` = activity name).

- [ ] **Step 1: Write the failing test**

```typescript
// destiny-weapon-advisor/frontend/src/recommend.test.ts
import { describe, expect, it } from "vitest";
import { buildContextOptions } from "./recommend";
import { ActivityRec } from "./types";

function activity(name: string): ActivityRec {
  return {
    name, type: "Raid", recommendedClass: "Any", recommendedSubclass: "Solar",
    weapons: "", notes: "",
  };
}

describe("buildContextOptions", () => {
  it("prepends general modes then lists activities", () => {
    const opts = buildContextOptions([activity("Crota's End"), activity("Last Wish")]);
    expect(opts).toEqual([
      { value: "general-pve", label: "General (PvE)" },
      { value: "general-pvp", label: "General (PvP)" },
      { value: "Crota's End", label: "Crota's End" },
      { value: "Last Wish", label: "Last Wish" },
    ]);
  });

  it("works with no activities", () => {
    expect(buildContextOptions([])).toEqual([
      { value: "general-pve", label: "General (PvE)" },
      { value: "general-pvp", label: "General (PvP)" },
    ]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd destiny-weapon-advisor/frontend && npm test -- recommend`
Expected: FAIL — cannot resolve `./recommend`.

- [ ] **Step 3: Add types**

In `destiny-weapon-advisor/frontend/src/types.ts`, append:

```typescript
export type RecommendedWeapon = WeaponDto & { recommendReason: string };

export interface Recommendations {
  context: string;
  slots: Record<"Primary" | "Special" | "Heavy", RecommendedWeapon[]>;
}
```

- [ ] **Step 4: Create the helper**

```typescript
// destiny-weapon-advisor/frontend/src/recommend.ts
import { ActivityRec } from "./types";

export function buildContextOptions(
  activities: ActivityRec[],
): { value: string; label: string }[] {
  return [
    { value: "general-pve", label: "General (PvE)" },
    { value: "general-pvp", label: "General (PvP)" },
    ...activities.map((a) => ({ value: a.name, label: a.name })),
  ];
}
```

- [ ] **Step 5: Add the API client function**

In `destiny-weapon-advisor/frontend/src/api.ts`, add `Recommendations` to the import from `./types`, then append:

```typescript
export async function fetchRecommendations(context: string): Promise<Recommendations> {
  const res = await fetch(`/api/recommendations?context=${encodeURIComponent(context)}`);
  if (!res.ok) throw new Error(`Failed to load recommendations (${res.status})`);
  return (await res.json()) as Recommendations;
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd destiny-weapon-advisor/frontend && npm test -- recommend`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
cd <REPO_ROOT>
git add destiny-weapon-advisor/frontend/src/types.ts destiny-weapon-advisor/frontend/src/api.ts destiny-weapon-advisor/frontend/src/recommend.ts destiny-weapon-advisor/frontend/src/recommend.test.ts
git commit -m "feat: frontend recommendations api + context options helper"
```

---

### Task 4: "Recommend" tab UI

**Files:**
- Create: `destiny-weapon-advisor/frontend/src/components/RecommendPage.tsx`
- Modify: `destiny-weapon-advisor/frontend/src/components/Nav.tsx` (add section)
- Modify: `destiny-weapon-advisor/frontend/src/App.tsx` (import + render)

**Interfaces:**
- Consumes: `fetchRecommendations`, `fetchActivities` (api), `buildContextOptions` (recommend.ts), `WeaponCard` (component), `Recommendations` (types).
- Produces: a `RecommendPage` React component and a `"recommend"` nav section.

- [ ] **Step 1: Add the nav section**

In `destiny-weapon-advisor/frontend/src/components/Nav.tsx`:

Change the `Section` type to include `"recommend"`:

```typescript
export type Section = "weapons" | "recommend" | "perks" | "armor" | "builds" | "activities" | "loadouts";
```

Add to `SECTIONS` right after the `weapons` entry:

```typescript
  { id: "recommend", label: "Recommend" },
```

- [ ] **Step 2: Create the page component**

```tsx
// destiny-weapon-advisor/frontend/src/components/RecommendPage.tsx
import { useEffect, useState } from "react";
import { fetchActivities, fetchRecommendations } from "../api";
import { buildContextOptions } from "../recommend";
import { ActivityRec, Recommendations } from "../types";
import { WeaponCard } from "./WeaponCard";

const SLOTS: ("Primary" | "Special" | "Heavy")[] = ["Primary", "Special", "Heavy"];

export function RecommendPage() {
  const [activities, setActivities] = useState<ActivityRec[]>([]);
  const [context, setContext] = useState("general-pve");
  const [data, setData] = useState<Recommendations | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchActivities().then(setActivities).catch(() => setActivities([]));
  }, []);

  useEffect(() => {
    setError("");
    fetchRecommendations(context).then(setData).catch((e) => setError(String(e)));
  }, [context]);

  const options = buildContextOptions(activities);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>Recommended Weapons</h1>
        <select
          value={context}
          onChange={(e) => setContext(e.target.value)}
          style={{
            background: "var(--panel)", color: "var(--text, inherit)",
            border: "1px solid var(--border)", borderRadius: 6, padding: "6px 10px",
          }}
        >
          {options.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      {context === "general-pvp" && (
        <p style={{ color: "var(--muted)", marginTop: 0 }}>
          Note: ratings are PvE-oriented. PvP-specific ratings are coming later.
        </p>
      )}

      {error && <p style={{ color: "#c62828" }}>{error}</p>}

      {data && SLOTS.map((slot) => (
        <section key={slot} style={{ marginBottom: 24 }}>
          <h2 style={{ borderBottom: "1px solid var(--border)", paddingBottom: 6 }}>{slot}</h2>
          {data.slots[slot].length === 0 ? (
            <p style={{ color: "var(--muted)" }}>No qualifying weapons. Refresh your vault on the Weapons tab.</p>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 10 }}>
              {data.slots[slot].map((w) => (
                <div key={w.instanceId}>
                  <WeaponCard w={w} onClick={() => {}} />
                  <div style={{ fontSize: 12, color: "var(--muted)", padding: "2px 10px 0" }}>
                    {w.recommendReason}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Wire into App**

In `destiny-weapon-advisor/frontend/src/App.tsx`:

Add the import alongside the other component imports:

```typescript
import { RecommendPage } from "./components/RecommendPage";
```

Add the render branch right after the `weapons` block (after its closing `</>` and `)}`):

```tsx
        {section === "recommend" && <RecommendPage />}
```

- [ ] **Step 4: Verify the build and tests pass**

Run: `cd destiny-weapon-advisor/frontend && npm run build && npm test`
Expected: build succeeds (no TS errors), all Vitest tests PASS.

- [ ] **Step 5: Commit**

```bash
cd <REPO_ROOT>
git add destiny-weapon-advisor/frontend/src/components/RecommendPage.tsx destiny-weapon-advisor/frontend/src/components/Nav.tsx destiny-weapon-advisor/frontend/src/App.tsx
git commit -m "feat: Recommend tab UI for best-from-vault recommendations"
```

---

## Self-Review Notes

- **Spec coverage:** ranking engine (Task 1), endpoint + context resolution + empty-cache fallback (Task 2), PvP caveat note + context dropdown + 3 slot sections + empty state (Task 4), tests at each layer (Tasks 1–4). All spec sections mapped.
- **Type consistency:** `recommend_weapons`/`element_for_subclass` signatures identical across Tasks 1–2; `Recommendations`/`RecommendedWeapon`/`buildContextOptions`/`fetchRecommendations` identical across Tasks 3–4; `Section` union extended consistently in Nav and consumed in App.
- **Verdict values** match `Verdict` enum verbatim. Ammo slot strings match across backend and frontend.
