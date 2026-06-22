# Save Armor Sets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user save the Armor Optimizer's 5-piece set as a named Armor Set (with a target character), list saved sets on the Armor page, and apply or delete them.

**Architecture:** A dedicated `armor_sets` SQLite table + CRUD/apply endpoints, mirroring the existing loadouts store but kept separate. The move/equip loop is extracted from `apply_loadout` into a shared `_apply_item_set` helper reused by both loadout-apply and armor-set-apply. The Armor page gains a save row and a saved-sets list; a pure helper builds the persisted items from the optimizer's `chosen` map.

**Tech Stack:** Python 3.13 + FastAPI + pytest (backend); React + TypeScript + Vitest (frontend).

## Global Constraints

- Armor sets are stored SEPARATELY from weapon loadouts (own `armor_sets` table).
- The Bungie move/equip loop must NOT be duplicated — loadout-apply and armor-set-apply share one `_apply_item_set` helper.
- Stored set `data` shape: `{className, characterId, tier, items:[{instanceId, itemHash, slot, name}]}`.
- Tier = floor(sum of ALL stat values across chosen pieces / 10).
- Canonical slot order: `Helmet, Gauntlets, Chest Armor, Leg Armor, Class Item`.
- Apply equips items via the existing transfer/equip path only (no new write scopes); unknown set name → 404.
- Backend tests run from `destiny-weapon-advisor/backend` via `pytest`; frontend from `destiny-weapon-advisor/frontend` via `npm test`.

---

### Task 1: Backend armor-sets store (table + CRUD endpoints)

**Files:**
- Modify: `destiny-weapon-advisor/backend/app/main.py` (add `ArmorSetBody`, `_ensure_armor_sets`, GET/PUT/DELETE endpoints)
- Test: `destiny-weapon-advisor/backend/tests/test_armor_sets.py`

**Interfaces:**
- Consumes: existing `get_conn`, `get_settings`, `json`, `BaseModel` (already imported in main.py).
- Produces:
  - `ArmorSetBody(name: str, className: str, characterId: str, tier: int, items: list[dict])`
  - `GET /api/armor-sets` → `{"armorSets": [{"name", "className", "characterId", "tier", "items"}]}`
  - `PUT /api/armor-sets` (body `ArmorSetBody`, upsert by name) → `{"ok": True}`
  - `DELETE /api/armor-sets/{name}` → `{"ok": True}`

- [ ] **Step 1: Write the failing test**

```python
# destiny-weapon-advisor/backend/tests/test_armor_sets.py
from fastapi.testclient import TestClient

from app.main import app

_SET = {
    "name": "pytest-armor-set",
    "className": "Warlock",
    "characterId": "char-123",
    "tier": 17,
    "items": [
        {"instanceId": "i1", "itemHash": 11, "slot": "Helmet", "name": "Ferropotent Cover"},
        {"instanceId": "i2", "itemHash": 22, "slot": "Class Item", "name": "Swordmaster's Bond"},
    ],
}


def test_put_get_delete_round_trip():
    client = TestClient(app)
    try:
        assert client.put("/api/armor-sets", json=_SET).status_code == 200
        body = client.get("/api/armor-sets").json()
        match = next((s for s in body["armorSets"] if s["name"] == "pytest-armor-set"), None)
        assert match is not None
        assert match["className"] == "Warlock"
        assert match["characterId"] == "char-123"
        assert match["tier"] == 17
        assert len(match["items"]) == 2
        assert match["items"][0]["slot"] == "Helmet"
    finally:
        assert client.delete("/api/armor-sets/pytest-armor-set").status_code == 200
    after = client.get("/api/armor-sets").json()["armorSets"]
    assert all(s["name"] != "pytest-armor-set" for s in after)


def test_put_upsert_overwrites():
    client = TestClient(app)
    try:
        client.put("/api/armor-sets", json=_SET)
        updated = {**_SET, "tier": 20}
        client.put("/api/armor-sets", json=updated)
        body = client.get("/api/armor-sets").json()["armorSets"]
        match = next(s for s in body if s["name"] == "pytest-armor-set")
        assert match["tier"] == 20
    finally:
        client.delete("/api/armor-sets/pytest-armor-set")


def test_put_missing_field_returns_422():
    client = TestClient(app)
    resp = client.put("/api/armor-sets", json={"name": "x"})
    assert resp.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd destiny-weapon-advisor/backend && python -m pytest tests/test_armor_sets.py -v`
Expected: FAIL (PUT returns 404/405 — route not defined).

- [ ] **Step 3: Add the model**

In `destiny-weapon-advisor/backend/app/main.py`, immediately after the existing `class ApplyLoadoutBody(BaseModel):` block (near line 89), add:

```python
class ArmorSetBody(BaseModel):
    name: str
    className: str
    characterId: str
    tier: int
    items: list[dict]  # [{instanceId, itemHash, slot, name}]
```

- [ ] **Step 4: Add the table helper + CRUD endpoints**

In `destiny-weapon-advisor/backend/app/main.py`, immediately after the `delete_loadout` endpoint function (the block ending its `return {"ok": True}`, near line 745), add:

```python
def _ensure_armor_sets(conn) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS armor_sets (name TEXT PRIMARY KEY, data TEXT)")
    conn.commit()


@app.get("/api/armor-sets")
def get_armor_sets() -> dict:
    conn = get_conn(get_settings().db_path)
    _ensure_armor_sets(conn)
    out = []
    for name, data in conn.execute("SELECT name, data FROM armor_sets"):
        out.append({"name": name, **json.loads(data)})
    return {"armorSets": out}


@app.put("/api/armor-sets")
def put_armor_set(body: ArmorSetBody) -> dict:
    conn = get_conn(get_settings().db_path)
    _ensure_armor_sets(conn)
    data = json.dumps({
        "className": body.className,
        "characterId": body.characterId,
        "tier": body.tier,
        "items": body.items,
    })
    conn.execute(
        "INSERT INTO armor_sets (name, data) VALUES (?, ?) "
        "ON CONFLICT(name) DO UPDATE SET data = excluded.data",
        (body.name, data),
    )
    conn.commit()
    return {"ok": True}


@app.delete("/api/armor-sets/{name}")
def delete_armor_set(name: str) -> dict:
    conn = get_conn(get_settings().db_path)
    _ensure_armor_sets(conn)
    conn.execute("DELETE FROM armor_sets WHERE name = ?", (name,))
    conn.commit()
    return {"ok": True}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd destiny-weapon-advisor/backend && python -m pytest tests/test_armor_sets.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
cd <REPO_ROOT>
git add destiny-weapon-advisor/backend/app/main.py destiny-weapon-advisor/backend/tests/test_armor_sets.py
git commit -m "feat: armor_sets store + CRUD endpoints"
```

---

### Task 2: Backend apply — extract shared helper + armor-set apply endpoint

**Files:**
- Modify: `destiny-weapon-advisor/backend/app/main.py` (extract `_apply_item_set`, refactor `apply_loadout`, add `POST /api/armor-sets/apply`)
- Test: `destiny-weapon-advisor/backend/tests/test_armor_sets_apply.py`

**Interfaces:**
- Consumes: `_ensure_armor_sets` (Task 1); existing `_load_profile_or_400`, `_valid_access_token`, `_move_one`, `get_profile`, `_save_profile`, `httpx`, `BungieApiError`, `HTTPException`.
- Produces:
  - `async _apply_item_set(conn, settings, items: list[dict], target: str) -> list[dict]` — moves+equips each `{instanceId, itemHash}` to `target`, returns `[{instanceId, ok, error?}]`.
  - `POST /api/armor-sets/apply` (body `ApplyLoadoutBody` = `{name}`) → `{"results": [...]}`; 404 on unknown set.

- [ ] **Step 1: Write the failing test**

```python
# destiny-weapon-advisor/backend/tests/test_armor_sets_apply.py
from fastapi.testclient import TestClient

from app.main import app


def test_apply_unknown_set_returns_404_with_detail():
    client = TestClient(app)
    resp = client.post("/api/armor-sets/apply", json={"name": "does-not-exist-xyz"})
    assert resp.status_code == 404
    # Asserting the specific detail makes this a meaningful RED: before the route
    # exists FastAPI returns 404 with detail "Not Found"; only the implemented
    # route returns this message.
    assert resp.json()["detail"] == "Armor set not found."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd destiny-weapon-advisor/backend && python -m pytest tests/test_armor_sets_apply.py -v`
Expected: FAIL — the route doesn't exist yet, so FastAPI returns 404 with `detail == "Not Found"`, failing the detail assertion.

- [ ] **Step 3: Extract the shared helper**

In `destiny-weapon-advisor/backend/app/main.py`, locate the existing `apply_loadout` function. Add this helper immediately BEFORE it:

```python
async def _apply_item_set(conn, settings, items: list[dict], target: str) -> list[dict]:
    """Move+equip each {instanceId, itemHash} item to the target character.
    Returns per-item results. Shared by loadout-apply and armor-set-apply."""
    profile = _load_profile_or_400(conn)
    results = []
    async with httpx.AsyncClient(
        timeout=180.0, headers={"X-API-Key": settings.bungie_api_key}
    ) as client:
        access, mtype, mid = await _valid_access_token(settings, conn, client)
        for it in items:
            try:
                await _move_one(client, settings, access, mtype, profile, it["instanceId"],
                                it["itemHash"], target, True)
                results.append({"instanceId": it["instanceId"], "ok": True})
            except (BungieApiError, httpx.HTTPStatusError) as exc:
                results.append({"instanceId": it["instanceId"], "ok": False, "error": str(exc)})
        fresh = await get_profile(mtype, mid, access, settings, client)
    _save_profile(conn, fresh, mid)
    return results
```

- [ ] **Step 4: Refactor `apply_loadout` to use the helper**

Replace the body of `apply_loadout` (everything after the `loadout = json.loads(row[0])` line) so it delegates to the helper. The full refactored function:

```python
@app.post("/api/loadouts/apply")
async def apply_loadout(body: ApplyLoadoutBody) -> dict:
    settings = get_settings()
    conn = get_conn(settings.db_path)
    _ensure_loadouts(conn)
    row = conn.execute("SELECT data FROM loadouts WHERE name = ?", (body.name,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Loadout not found.")
    loadout = json.loads(row[0])
    results = await _apply_item_set(conn, settings, loadout["items"], loadout["characterId"])
    return {"results": results}
```

- [ ] **Step 5: Add the armor-set apply endpoint**

Immediately after `delete_armor_set` (from Task 1), add:

```python
@app.post("/api/armor-sets/apply")
async def apply_armor_set(body: ApplyLoadoutBody) -> dict:
    settings = get_settings()
    conn = get_conn(settings.db_path)
    _ensure_armor_sets(conn)
    row = conn.execute("SELECT data FROM armor_sets WHERE name = ?", (body.name,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Armor set not found.")
    armor_set = json.loads(row[0])
    results = await _apply_item_set(conn, settings, armor_set["items"], armor_set["characterId"])
    return {"results": results}
```

- [ ] **Step 6: Run the apply test + full suite**

Run: `cd destiny-weapon-advisor/backend && python -m pytest tests/test_armor_sets_apply.py -v`
Expected: PASS (1 test)

Run: `cd destiny-weapon-advisor/backend && python -m pytest -q`
Expected: ALL pass (existing loadout-apply tests confirm the refactor is behavior-preserving).

- [ ] **Step 7: Commit**

```bash
cd <REPO_ROOT>
git add destiny-weapon-advisor/backend/app/main.py destiny-weapon-advisor/backend/tests/test_armor_sets_apply.py
git commit -m "feat: shared _apply_item_set helper + armor-set apply endpoint"
```

---

### Task 3: Frontend types, API client, and pure helpers

**Files:**
- Modify: `destiny-weapon-advisor/frontend/src/types.ts` (add `ArmorSetItem`, `ArmorSet`)
- Modify: `destiny-weapon-advisor/frontend/src/api.ts` (add fetch/save/delete/apply)
- Create: `destiny-weapon-advisor/frontend/src/armorSet.ts` (pure `armorSetItems`, `armorSetTier`)
- Test: `destiny-weapon-advisor/frontend/src/armorSet.test.ts`

**Interfaces:**
- Consumes: existing `ArmorPiece`, `MoveResult`.
- Produces:
  - `ArmorSetItem = { instanceId: string; itemHash: number; slot: string; name: string }`
  - `ArmorSet = { name: string; className: string; characterId: string; tier: number; items: ArmorSetItem[] }`
  - `fetchArmorSets(): Promise<ArmorSet[]>`
  - `saveArmorSet(set: ArmorSet): Promise<void>`
  - `deleteArmorSet(name: string): Promise<void>`
  - `applyArmorSet(name: string): Promise<MoveResult[]>`
  - `armorSetItems(chosen: Record<string, ArmorPiece | null>): ArmorSetItem[]`
  - `armorSetTier(chosen: Record<string, ArmorPiece | null>): number`

- [ ] **Step 1: Write the failing test**

```typescript
// destiny-weapon-advisor/frontend/src/armorSet.test.ts
import { describe, expect, it } from "vitest";
import { armorSetItems, armorSetTier } from "./armorSet";
import { ArmorPiece } from "./types";

function piece(p: Partial<ArmorPiece>): ArmorPiece {
  return {
    instanceId: "i", itemHash: 1, name: "Piece", slot: "Helmet", className: "Warlock",
    power: 0, isExotic: false, isMasterworked: false, stats: {}, location: "Vault",
    icon: "", equipped: false, ...p,
  };
}

describe("armorSetItems", () => {
  it("maps non-null pieces in canonical slot order, skipping empties", () => {
    const chosen = {
      "Helmet": piece({ instanceId: "h", itemHash: 10, slot: "Helmet", name: "Helm" }),
      "Gauntlets": null,
      "Chest Armor": piece({ instanceId: "c", itemHash: 30, slot: "Chest Armor", name: "Chest" }),
      "Leg Armor": null,
      "Class Item": piece({ instanceId: "ci", itemHash: 50, slot: "Class Item", name: "Bond" }),
    };
    expect(armorSetItems(chosen)).toEqual([
      { instanceId: "h", itemHash: 10, slot: "Helmet", name: "Helm" },
      { instanceId: "c", itemHash: 30, slot: "Chest Armor", name: "Chest" },
      { instanceId: "ci", itemHash: 50, slot: "Class Item", name: "Bond" },
    ]);
  });

  it("returns empty array when all slots null", () => {
    expect(armorSetItems({ Helmet: null, Gauntlets: null })).toEqual([]);
  });
});

describe("armorSetTier", () => {
  it("floors the sum of all stat values over 10", () => {
    const chosen = {
      "Helmet": piece({ stats: { Class: 30, Health: 5 } }),  // 35
      "Class Item": piece({ stats: { Class: 40, Melee: 15 } }),  // 55
    };
    // total 90 -> tier 9
    expect(armorSetTier(chosen)).toBe(9);
  });

  it("is 0 for an all-null set", () => {
    expect(armorSetTier({ Helmet: null })).toBe(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd destiny-weapon-advisor/frontend && npm test -- armorSet`
Expected: FAIL — cannot resolve `./armorSet`.

- [ ] **Step 3: Add the types**

In `destiny-weapon-advisor/frontend/src/types.ts`, append:

```typescript
export interface ArmorSetItem {
  instanceId: string;
  itemHash: number;
  slot: string;
  name: string;
}

export interface ArmorSet {
  name: string;
  className: string;
  characterId: string;
  tier: number;
  items: ArmorSetItem[];
}
```

- [ ] **Step 4: Create the pure helpers**

```typescript
// destiny-weapon-advisor/frontend/src/armorSet.ts
import { ArmorPiece, ArmorSetItem } from "./types";

const SLOTS = ["Helmet", "Gauntlets", "Chest Armor", "Leg Armor", "Class Item"];

export function armorSetItems(chosen: Record<string, ArmorPiece | null>): ArmorSetItem[] {
  const items: ArmorSetItem[] = [];
  for (const slot of SLOTS) {
    const p = chosen[slot];
    if (p) items.push({ instanceId: p.instanceId, itemHash: p.itemHash, slot, name: p.name });
  }
  return items;
}

export function armorSetTier(chosen: Record<string, ArmorPiece | null>): number {
  let total = 0;
  for (const slot of SLOTS) {
    const p = chosen[slot];
    if (p) total += Object.values(p.stats).reduce((a, b) => a + b, 0);
  }
  return Math.floor(total / 10);
}
```

- [ ] **Step 5: Add the API client functions**

In `destiny-weapon-advisor/frontend/src/api.ts`, add `ArmorSet` to the import from `./types`, then append:

```typescript
export async function fetchArmorSets(): Promise<ArmorSet[]> {
  const res = await fetch("/api/armor-sets");
  if (!res.ok) throw new Error(`Failed to load armor sets (${res.status})`);
  return (await res.json()).armorSets as ArmorSet[];
}

export async function saveArmorSet(set: ArmorSet): Promise<void> {
  const res = await fetch("/api/armor-sets", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(set),
  });
  if (!res.ok) throw new Error(`Failed to save armor set (${res.status})`);
}

export async function deleteArmorSet(name: string): Promise<void> {
  const res = await fetch(`/api/armor-sets/${encodeURIComponent(name)}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Failed to delete armor set (${res.status})`);
}

export async function applyArmorSet(name: string): Promise<MoveResult[]> {
  const res = await fetch("/api/armor-sets/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(data.detail || `Apply failed (${res.status})`);
  }
  return (await res.json()).results as MoveResult[];
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd destiny-weapon-advisor/frontend && npm test -- armorSet`
Expected: PASS (4 tests).

- [ ] **Step 7: Commit**

```bash
cd <REPO_ROOT>
git add destiny-weapon-advisor/frontend/src/types.ts destiny-weapon-advisor/frontend/src/api.ts destiny-weapon-advisor/frontend/src/armorSet.ts destiny-weapon-advisor/frontend/src/armorSet.test.ts
git commit -m "feat: frontend armor-sets api + pure items/tier helpers"
```

---

### Task 4: Armor page — save row + saved-sets list

**Files:**
- Modify: `destiny-weapon-advisor/frontend/src/components/ArmorPage.tsx`

**Interfaces:**
- Consumes: `fetchCharacters`, `fetchArmorSets`, `saveArmorSet`, `deleteArmorSet`, `applyArmorSet` (api); `armorSetItems`, `armorSetTier` (helper); `Character`, `ArmorSet` (types); the existing `chosen` and `cls` values in ArmorPage.

- [ ] **Step 1: Add imports and state**

In `destiny-weapon-advisor/frontend/src/components/ArmorPage.tsx`:

Change the existing api import line:
```typescript
import { fetchArmor } from "../api";
```
to:
```typescript
import {
  applyArmorSet, deleteArmorSet, fetchArmor, fetchArmorSets, fetchCharacters, saveArmorSet,
} from "../api";
```

Change the types import line:
```typescript
import { ArmorPiece } from "../types";
```
to:
```typescript
import { ArmorPiece, ArmorSet, Character } from "../types";
```

Add the helper import:
```typescript
import { armorSetItems, armorSetTier } from "../armorSet";
```

Inside the `ArmorPage` component, after the existing `const [mins, setMins] = useState<Record<string, number>>({});` line, add:

```typescript
  const [characters, setCharacters] = useState<Character[]>([]);
  const [armorSets, setArmorSets] = useState<ArmorSet[]>([]);
  const [setName, setSetName] = useState("");
  const [targetChar, setTargetChar] = useState("");
  const [saveMsg, setSaveMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchCharacters().then(setCharacters).catch(() => setCharacters([]));
    fetchArmorSets().then(setArmorSets).catch(() => setArmorSets([]));
  }, []);

  const classChars = useMemo(
    () => characters.filter((c) => c.className === cls),
    [characters, cls],
  );

  useEffect(() => {
    setTargetChar(classChars[0]?.id ?? "");
  }, [classChars]);

  const setItems = useMemo(() => armorSetItems(chosen), [chosen]);

  async function saveSet() {
    if (!setName.trim() || !targetChar || setItems.length === 0) {
      setSaveMsg("Enter a name and pick a character of this class.");
      return;
    }
    setBusy(true);
    setSaveMsg("");
    try {
      await saveArmorSet({
        name: setName.trim(), className: cls, characterId: targetChar,
        tier: armorSetTier(chosen), items: setItems,
      });
      setSaveMsg(`Saved "${setName.trim()}".`);
      setSetName("");
      fetchArmorSets().then(setArmorSets);
    } catch (e) {
      setSaveMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function applySet(s: ArmorSet) {
    if (!window.confirm(`Apply "${s.name}"? This moves & equips ${s.items.length} pieces.`)) return;
    setBusy(true);
    setSaveMsg("");
    try {
      const results = await applyArmorSet(s.name);
      const fail = results.filter((r) => !r.ok).length;
      setSaveMsg(fail ? `Applied with ${fail} issue(s) — if it's a permission error, click Re-login.`
        : `✓ Applied "${s.name}".`);
    } catch (e) {
      setSaveMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function removeSet(s: ArmorSet) {
    if (!window.confirm(`Delete armor set "${s.name}"?`)) return;
    await deleteArmorSet(s.name);
    fetchArmorSets().then(setArmorSets);
  }
```

NOTE: `useMemo` and `useEffect` are already imported (the file uses both). `chosen` and `cls` are already defined above in the component.

- [ ] **Step 2: Add the save row + saved-sets list to the render**

In `destiny-weapon-advisor/frontend/src/components/ArmorPage.tsx`, find the closing `</p>` of the existing footer note (the paragraph that starts "Best owned pieces per slot, max one exotic."). Immediately AFTER that `</p>`, and before the component's final `</div>`, insert:

```tsx
      {saveMsg && (
        <p style={{ color: saveMsg.startsWith("✓") || saveMsg.startsWith("Saved") ? "#2e7d32" : "#c62828" }}>
          {saveMsg}
        </p>
      )}

      <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 14, marginTop: 16, marginBottom: 20, maxWidth: 640 }}>
        <strong>Save this set</strong>
        <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
          <input
            placeholder="Set name…" value={setName}
            onChange={(e) => setSetName(e.target.value)}
          />
          <select value={targetChar} onChange={(e) => setTargetChar(e.target.value)}>
            {classChars.length === 0 && <option value="">No {cls} character</option>}
            {classChars.map((c) => <option key={c.id} value={c.id}>{c.className} ✦{c.light}</option>)}
          </select>
          <button onClick={saveSet} disabled={busy || !setItems.length || !targetChar}>Save</button>
        </div>
        <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>
          Saves {setItems.length} piece(s) · Tier {armorSetTier(chosen)} for {cls}.
        </div>
      </div>

      <h2 style={{ marginTop: 8 }}>Saved armor sets</h2>
      {armorSets.length === 0 && <p style={{ color: "var(--muted)" }}>None yet.</p>}
      {armorSets.map((s) => (
        <div key={s.name} style={{
          display: "flex", alignItems: "center", gap: 12, border: "1px solid var(--border)",
          borderRadius: 8, padding: "8px 12px", marginBottom: 8, maxWidth: 640,
        }}>
          <strong style={{ flex: 1 }}>{s.name}</strong>
          <span style={{ color: "var(--muted)", fontSize: 13 }}>{s.className} · Tier {s.tier} · {s.items.length} pieces</span>
          <button onClick={() => applySet(s)} disabled={busy}>Apply</button>
          <button onClick={() => removeSet(s)} disabled={busy} style={{ color: "#c62828" }}>Delete</button>
        </div>
      ))}
```

- [ ] **Step 3: Verify the build and tests pass**

Run: `cd destiny-weapon-advisor/frontend && npm run build && npm test`
Expected: build succeeds (no TS errors); all Vitest tests PASS.

- [ ] **Step 4: Commit**

```bash
cd <REPO_ROOT>
git add destiny-weapon-advisor/frontend/src/components/ArmorPage.tsx
git commit -m "feat: save/list/apply armor sets on the Armor page"
```

---

## Self-Review Notes

- **Spec coverage:** table + CRUD (Task 1), shared apply helper + apply endpoint + refactor regression (Task 2), types/api/pure helpers (Task 3), save row + saved-sets list with apply/delete (Task 4). All spec sections mapped.
- **Type consistency:** `ArmorSetBody` (backend) ↔ `ArmorSet`/`ArmorSetItem` (frontend) field names match (`className`, `characterId`, `tier`, `items[].slot/name`). `_apply_item_set` signature identical Task 2 internal use. `armorSetItems`/`armorSetTier` signatures identical Task 3↔4.
- **DRY:** apply loop extracted once; loadout-apply rewritten to call it (verified by existing tests in Task 2 Step 6).
- **Stored-shape note:** `GET` returns `{name, ...data}` so the frontend `ArmorSet` (which includes `name`) is satisfied; `PUT` stores `data` without `name` (name is the PK column) — consistent with the loadouts pattern.
- **Open item for executor:** confirm `Character` has `id` and `light` fields (used in the dropdown) — the Loadouts page already relies on both, so they exist; verify during Task 4.
